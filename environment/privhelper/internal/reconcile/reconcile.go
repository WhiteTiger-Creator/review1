// Package reconcile summarizes dispatcher state into the authority report.
package reconcile

import (
	"encoding/json"
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
	rep := report.Report{
		Violations:       []string{},
		HelpersTrusted:   true,
		RecoveryComplete: true,
		IdempotencySound: true,
		Journal:          rc.Paths.Journal(),
		DecisionLog:      rc.Paths.Decisions(),
		EffectLog:        rc.Paths.Effects(),
		Manifest:         rc.Paths.Manifest(),
		Trace:            tracePath,
	}

	loaded, err := rc.Manifests.LoadCurrent()
	if err != nil {
		rep.Violations = append(rep.Violations, "manifest_unverified: "+err.Error())
		rep.HelpersTrusted = false
		trace = append(trace, traceRecord{"phase": "verify_manifest", "ok": false, "error": err.Error()})
		rep.AuthoritySound = false
		_ = writeTrace(tracePath, trace)
		_ = report.Write(outputPath, rep)
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
		}
	}

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
	}

	pending := 0
	for _, ev := range events {
		if ev.Event == journal.KindPrepared {
			_ = ev
		}
	}

	rep.RequestsSeen = len(seenRequests)
	rep.CommittedRequests = committedReq
	rep.DeniedRequests = deniedReq
	rep.ConflictRequests = conflictReq
	rep.PendingRequests = pending
	rep.EffectsApplied = len(effects)
	rep.IdempotencySound = true
	rep.RecoveryComplete = true
	_ = helperNames

	digest, err := report.ComputeLedgerDigest(rc.Paths)
	if err != nil {
		return rep, err
	}
	rep.LedgerDigest = digest
	rep.AuthoritySound = len(rep.Violations) == 0

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

func writeTrace(path string, records []traceRecord) error {
	if path == "" {
		return nil
	}
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
