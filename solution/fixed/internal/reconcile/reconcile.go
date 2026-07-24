// Package reconcile independently re-derives dispatcher state from the signed
// manifest, live helper artifacts, journal, and ledgers, and emits the sealed
// authority report. It trusts nothing that it cannot re-verify.
package reconcile

import (
	"encoding/json"
	"fmt"
	"sort"

	"privhelper/internal/fsutil"
	"privhelper/internal/helper"
	"privhelper/internal/journal"
	"privhelper/internal/ledger"
	"privhelper/internal/manifest"
	"privhelper/internal/model"
	"privhelper/internal/report"
)

// Reconciler recomputes the authority report.
type Reconciler struct {
	Paths     model.Paths
	Manifests *manifest.Store
	Journal   *journal.Store
	Decisions *ledger.DecisionStore
	Effects   *ledger.EffectStore
}

// New builds a Reconciler.
func New(p model.Paths) *Reconciler {
	return &Reconciler{
		Paths:     p,
		Manifests: manifest.NewStore(p),
		Journal:   journal.NewStore(p),
		Decisions: ledger.NewDecisionStore(p),
		Effects:   ledger.NewEffectStore(p),
	}
}

type traceRecord map[string]any

// Run reconciles state, writes the trace, and writes the report.
func (rc *Reconciler) Run(tracePath, outputPath string) (report.Report, error) {
	var trace []traceRecord
	violations := []string{}

	rep := report.Report{
		Violations:       violations,
		HelpersTrusted:   true,
		RecoveryComplete: true,
		IdempotencySound: true,
		Journal:          rc.Paths.Journal(),
		DecisionLog:      rc.Paths.Decisions(),
		EffectLog:        rc.Paths.Effects(),
		Manifest:         rc.Paths.Manifest(),
		Trace:            tracePath,
	}

	// Phase 1: independently verify the signed manifest and its digest.
	loaded, err := rc.Manifests.LoadCurrent()
	if err != nil {
		rep.Violations = append(rep.Violations, "manifest_unverified: "+err.Error())
		rep.HelpersTrusted = false
		trace = append(trace, traceRecord{"phase": "verify_manifest", "ok": false, "error": err.Error()})
		rep.AuthoritySound = false
		if werr := writeTrace(tracePath, trace); werr != nil {
			return rep, werr
		}
		if werr := report.Write(outputPath, rep); werr != nil {
			return rep, werr
		}
		return rep, nil
	}
	man := loaded.Manifest
	rep.Scenario = man.Scenario
	rep.ManifestGeneration = man.Generation
	rep.ManifestDigest = loaded.Digest
	trace = append(trace, traceRecord{
		"phase":               "verify_manifest",
		"ok":                  true,
		"scenario":            man.Scenario,
		"manifest_generation": man.Generation,
		"manifest_digest":     loaded.Digest,
	})

	// Phase 2: independently verify every live helper artifact.
	helperNames := make([]string, 0, len(man.Helpers))
	for name := range man.Helpers {
		helperNames = append(helperNames, name)
	}
	sort.Strings(helperNames)
	for _, name := range helperNames {
		res := helper.Resolve(rc.Paths, man, name)
		trace = append(trace, traceRecord{
			"phase":        "verify_helper",
			"helper_name":  name,
			"helper_path":  res.Path,
			"helper_trust": res.Trusted,
			"reason":       res.Reason,
		})
		if !res.Trusted {
			rep.HelpersTrusted = false
			rep.Violations = append(rep.Violations, fmt.Sprintf("helper_untrusted:%s:%s", name, res.Reason))
		}
	}

	// Phase 3: load durable state.
	events, err := rc.Journal.LoadAll()
	if err != nil {
		return rep, err
	}
	decisions, err := rc.Decisions.LoadAll()
	if err != nil {
		return rep, err
	}
	effects, err := rc.Effects.LoadAll()
	if err != nil {
		return rep, err
	}

	// Phase 4: rebuild per-request state from the journal and detect ordering
	// contradictions.
	type jstate struct {
		prepared       bool
		effectApplied  bool
		committed      bool
		denied         bool
		conflict       bool
		recoveryDenied bool
		digests        map[string]bool
	}
	jstates := map[string]*jstate{}
	get := func(id string) *jstate {
		st, ok := jstates[id]
		if !ok {
			st = &jstate{digests: map[string]bool{}}
			jstates[id] = st
		}
		return st
	}
	for _, ev := range events {
		st := get(ev.RequestID)
		if ev.RequestDigest != "" {
			st.digests[ev.RequestDigest] = true
		}
		switch ev.Event {
		case journal.KindPrepared:
			st.prepared = true
		case journal.KindEffectApplied:
			if !st.prepared {
				rep.Violations = append(rep.Violations,
					"journal_order:effect_applied_before_prepared:"+ev.RequestID)
			}
			st.effectApplied = true
		case journal.KindCommitted:
			if !st.prepared {
				rep.Violations = append(rep.Violations,
					"journal_order:committed_before_prepared:"+ev.RequestID)
			}
			if !st.effectApplied {
				rep.Violations = append(rep.Violations,
					"journal_order:committed_without_effect_applied:"+ev.RequestID)
			}
			st.committed = true
		case journal.KindDenied:
			st.denied = true
		case journal.KindConflict:
			st.conflict = true
		case journal.KindRecoveryDenied:
			st.recoveryDenied = true
		}
	}

	// Unresolved pending: prepared but neither committed nor terminally denied.
	pending := 0
	for id, st := range jstates {
		if st.prepared && !st.committed && !st.denied && !st.recoveryDenied {
			pending++
			rep.RecoveryComplete = false
			rep.Violations = append(rep.Violations, "unresolved_pending:"+id)
		}
		// Body substitution: a single request id carrying more than one distinct
		// digest is only acceptable if it was recorded as a conflict.
		if len(st.digests) > 1 && !st.conflict {
			rep.Violations = append(rep.Violations, "body_substitution:"+id)
		}
	}

	// Phase 5: bind decisions and effects by (request_id, request_digest) and
	// verify their integrity against the manifest.
	seenRequests := map[string]bool{}
	committedReq := 0
	deniedReq := 0
	conflictReq := 0
	for _, d := range decisions {
		seenRequests[d.RequestID] = true
		switch d.Decision {
		case model.DecisionAllow:
			committedReq++
		case model.DecisionDeny:
			deniedReq++
		case model.DecisionConflict:
			conflictReq++
		}
		// Every allow decision must reference a manifest-trusted helper digest.
		if d.Decision == model.DecisionAllow {
			entry, ok := man.Helpers[d.HelperName]
			if !ok {
				rep.Violations = append(rep.Violations, "decision_helper_unknown:"+d.RequestID)
			} else if d.HelperDigest != entry.SHA256 {
				rep.Violations = append(rep.Violations, "decision_helper_digest_mismatch:"+d.RequestID)
			}
		}
	}

	effectKey := map[string]int{}
	for _, e := range effects {
		key := e.RequestID + "\x00" + e.RequestDigest
		effectKey[key]++
		// Effect must match the manifest effect / digest for its helper.
		if entry, ok := man.Helpers[e.HelperName]; !ok {
			rep.Violations = append(rep.Violations, "effect_helper_unknown:"+e.RequestID)
		} else {
			if e.Effect != entry.Effect {
				rep.Violations = append(rep.Violations, "effect_manifest_mismatch:"+e.RequestID)
			}
			if e.HelperDigest != entry.SHA256 {
				rep.Violations = append(rep.Violations, "effect_helper_digest_mismatch:"+e.RequestID)
			}
		}
		// Orphan effect: no committed allow decision binds this effect.
		if !committedBinds(decisions, e.RequestID, e.RequestDigest) {
			rep.Violations = append(rep.Violations, "orphan_effect:"+e.RequestID)
		}
	}

	// Duplicate effects: the same request identity must apply an effect at most
	// once.
	for key, n := range effectKey {
		if n > 1 {
			rep.IdempotencySound = false
			rep.Violations = append(rep.Violations, "duplicate_effect:"+key)
		}
	}

	rep.RequestsSeen = len(seenRequests)
	rep.CommittedRequests = committedReq
	rep.DeniedRequests = deniedReq
	rep.ConflictRequests = conflictReq
	rep.PendingRequests = pending
	rep.EffectsApplied = len(effects)

	// Phase 6: seal with the deterministic ledger digest.
	digest, err := report.ComputeLedgerDigest(rc.Paths)
	if err != nil {
		return rep, err
	}
	rep.LedgerDigest = digest

	rep.AuthoritySound = len(rep.Violations) == 0 &&
		rep.HelpersTrusted &&
		rep.RecoveryComplete &&
		rep.IdempotencySound

	trace = append(trace, traceRecord{
		"phase":              "reconcile",
		"authority_sound":    rep.AuthoritySound,
		"violations":         rep.Violations,
		"requests_seen":      rep.RequestsSeen,
		"committed_requests": rep.CommittedRequests,
		"denied_requests":    rep.DeniedRequests,
		"conflict_requests":  rep.ConflictRequests,
		"pending_requests":   rep.PendingRequests,
		"effects_applied":    rep.EffectsApplied,
		"ledger_digest":      rep.LedgerDigest,
	})

	if err := writeTrace(tracePath, trace); err != nil {
		return rep, err
	}
	if err := report.Write(outputPath, rep); err != nil {
		return rep, err
	}
	return rep, nil
}

func committedBinds(decisions []ledger.Decision, requestID, digest string) bool {
	for _, d := range decisions {
		if d.RequestID == requestID && d.RequestDigest == digest && d.Decision == model.DecisionAllow {
			return true
		}
	}
	return false
}

func writeTrace(path string, records []traceRecord) error {
	if path == "" {
		return nil
	}
	// Fresh trace per run.
	if err := fsutil.WriteFileSync(path, []byte{}, 0o644); err != nil {
		return err
	}
	for _, rec := range records {
		line, err := json.Marshal(rec)
		if err != nil {
			return err
		}
		if err := fsutil.AppendLineSync(path, line); err != nil {
			return err
		}
	}
	return nil
}
