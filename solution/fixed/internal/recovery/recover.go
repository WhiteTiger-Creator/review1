// Package recovery reconstructs dispatcher state from the durable journal after
// a crash. It never trusts stored "authorized" flags: every incomplete request
// is re-evaluated against the CURRENT signed manifest, and effects are never
// applied more than once.
package recovery

import (
	"fmt"

	"privhelper/internal/canonical"
	"privhelper/internal/helper"
	"privhelper/internal/journal"
	"privhelper/internal/ledger"
	"privhelper/internal/manifest"
	"privhelper/internal/model"
	"privhelper/internal/policy"
)

// Recoverer completes or denies requests left incomplete by a crash.
type Recoverer struct {
	Paths     model.Paths
	Manifests *manifest.Store
	Journal   *journal.Store
	Decisions *ledger.DecisionStore
	Effects   *ledger.EffectStore
}

// New builds a Recoverer.
func New(p model.Paths) *Recoverer {
	return &Recoverer{
		Paths:     p,
		Manifests: manifest.NewStore(p),
		Journal:   journal.NewStore(p),
		Decisions: ledger.NewDecisionStore(p),
		Effects:   ledger.NewEffectStore(p),
	}
}

// Summary reports what recovery did.
type Summary struct {
	Completed    int `json:"completed"`
	Committed    int `json:"committed"`
	Denied       int `json:"denied"`
	AlreadyDone  int `json:"already_complete"`
	Reevaluated  int `json:"reevaluated"`
	PendingFound int `json:"pending_found"`
}

type reqState struct {
	requestID     string
	prepared      *journal.Event
	effectApplied *journal.Event
	committed     bool
	recoveryDone  bool
}

// SetTrace mirrors recovery journal events to a trace file.
func (r *Recoverer) SetTrace(path string) {
	if path == "" {
		r.Journal.Trace = nil
		return
	}
	r.Journal.Trace = &journal.Trace{Path: path}
}

// Run performs one idempotent recovery pass.
func (r *Recoverer) Run() (Summary, error) {
	var sum Summary

	events, err := r.Journal.LoadAll()
	if err != nil {
		return sum, err
	}

	states := map[string]*reqState{}
	order := []string{}
	for i := range events {
		ev := events[i]
		st, ok := states[ev.RequestID]
		if !ok {
			st = &reqState{requestID: ev.RequestID}
			states[ev.RequestID] = st
			order = append(order, ev.RequestID)
		}
		switch ev.Event {
		case journal.KindPrepared:
			e := ev
			st.prepared = &e
		case journal.KindEffectApplied:
			e := ev
			st.effectApplied = &e
		case journal.KindCommitted:
			st.committed = true
		case journal.KindRecoveryDenied, journal.KindDenied, journal.KindConflict:
			st.recoveryDone = true
		}
	}

	for _, id := range order {
		st := states[id]
		if st.prepared == nil {
			// No prepare means nothing to complete (deny/conflict are terminal).
			continue
		}
		if st.committed {
			sum.AlreadyDone++
			continue
		}
		sum.PendingFound++

		if st.effectApplied != nil {
			if err := r.commitAlreadyApplied(st); err != nil {
				return sum, err
			}
			sum.Committed++
			sum.Completed++
			continue
		}

		// Prepared with no effect: re-authorize against the current manifest.
		sum.Reevaluated++
		completed, err := r.reevaluateAndComplete(st)
		if err != nil {
			return sum, err
		}
		if completed {
			sum.Completed++
		} else {
			sum.Denied++
		}
	}

	return sum, nil
}

// commitAlreadyApplied finalizes a request whose effect was applied before a
// crash. It verifies the recorded effect against the current manifest and then
// writes the decision + committed event exactly once; it NEVER re-executes.
func (r *Recoverer) commitAlreadyApplied(st *reqState) error {
	prep := st.prepared
	applied := st.effectApplied

	loaded, err := r.Manifests.LoadCurrent()
	if err != nil {
		return r.recoveryDeny(prep, model.LoadedManifest{}, helper.Resolution{}, fmt.Sprintf("manifest_unavailable_during_recovery: %v", err))
	}
	res := helper.ResolveByAction(r.Paths, loaded.Manifest, prep.Action)

	// Verify the applied effect matches what the current manifest expects for
	// this action.
	if res.Entry.Effect == "" || applied.Outcome != res.Entry.Effect {
		return r.recoveryDeny(prep, loaded, res, "recovered_effect_mismatch")
	}

	existing, hasDecision, err := r.Decisions.FindByRequestID(prep.RequestID)
	if err != nil {
		return err
	}
	if !hasDecision {
		rec := ledger.Decision{
			Seq:                prep.EventSeq,
			RequestID:          prep.RequestID,
			RequestDigest:      prep.RequestDigest,
			Principal:          prep.Principal,
			Action:             prep.Action,
			Unit:               prep.Unit,
			Decision:           model.DecisionAllow,
			Outcome:            applied.Outcome,
			Reason:             "recovered_commit",
			HelperName:         res.Name,
			HelperPath:         res.Path,
			HelperDigest:       res.Digest,
			ManifestGeneration: loaded.Manifest.Generation,
			ManifestDigest:     loaded.Digest,
			LaunchSurface:      "recovery",
		}
		if err := r.Decisions.Append(rec); err != nil {
			return err
		}
	} else {
		_ = existing
	}

	committed := &journal.Event{
		Event:              journal.KindCommitted,
		RequestID:          prep.RequestID,
		RequestDigest:      prep.RequestDigest,
		Principal:          prep.Principal,
		Action:             prep.Action,
		Unit:               prep.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionAllow,
		Outcome:            applied.Outcome,
		Reason:             "recovered_commit",
	}
	return r.Journal.Emit(committed)
}

// reevaluateAndComplete re-authorizes a prepared-only request and either
// executes+commits it once, or denies it via recovery_denied.
func (r *Recoverer) reevaluateAndComplete(st *reqState) (bool, error) {
	prep := st.prepared

	loaded, err := r.Manifests.LoadCurrent()
	if err != nil {
		return false, r.recoveryDeny(prep, model.LoadedManifest{}, helper.Resolution{}, fmt.Sprintf("manifest_unavailable_during_recovery: %v", err))
	}
	man := loaded.Manifest

	auth := policy.Authorize(man, prep.Principal, prep.Action)
	res := helper.ResolveByAction(r.Paths, man, prep.Action)

	if !auth.Authorized {
		return false, r.recoveryDeny(prep, loaded, res, "authority_revoked: "+auth.Reason)
	}
	if !res.Trusted {
		return false, r.recoveryDeny(prep, loaded, res, "helper_untrusted_on_recovery: "+res.Reason)
	}

	req := model.Request{
		RequestID: prep.RequestID,
		Principal: prep.Principal,
		Action:    prep.Action,
		Unit:      prep.Unit,
	}
	if err := canonical.ValidateRequest(req); err != nil {
		return false, r.recoveryDeny(prep, loaded, res, "prepared_request_invalid: "+err.Error())
	}
	if canonical.Digest(req) != prep.RequestDigest {
		return false, r.recoveryDeny(prep, loaded, res, "prepared_request_digest_mismatch")
	}
	binding := model.Binding{
		RequestDigest:      prep.RequestDigest,
		ManifestGeneration: man.Generation,
		ManifestDigest:     loaded.Digest,
	}

	exec, err := helper.Execute(res, req, binding)
	if err != nil {
		return false, r.recoveryDeny(prep, loaded, res, fmt.Sprintf("helper_execution_failed_on_recovery: %v", err))
	}

	// Complete the request exactly once: effect row, effect_applied, decision,
	// committed.
	effect := ledger.Effect{
		Seq:                prep.EventSeq,
		RequestID:          prep.RequestID,
		RequestDigest:      prep.RequestDigest,
		Principal:          prep.Principal,
		Action:             prep.Action,
		Unit:               prep.Unit,
		Effect:             exec.Effect,
		HelperName:         res.Name,
		HelperPath:         res.Path,
		HelperDigest:       res.Digest,
		ManifestGeneration: man.Generation,
		ManifestDigest:     loaded.Digest,
	}
	if err := r.Effects.Append(effect); err != nil {
		return false, err
	}

	applied := &journal.Event{
		Event:              journal.KindEffectApplied,
		RequestID:          prep.RequestID,
		RequestDigest:      prep.RequestDigest,
		Principal:          prep.Principal,
		Action:             prep.Action,
		Unit:               prep.Unit,
		ManifestGeneration: man.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Outcome:            exec.Effect,
		Reason:             "recovered_effect_applied",
	}
	if err := r.Journal.Emit(applied); err != nil {
		return false, err
	}

	if _, hasDecision, err := r.Decisions.FindByRequestID(prep.RequestID); err != nil {
		return false, err
	} else if !hasDecision {
		rec := ledger.Decision{
			Seq:                prep.EventSeq,
			RequestID:          prep.RequestID,
			RequestDigest:      prep.RequestDigest,
			Principal:          prep.Principal,
			Action:             prep.Action,
			Unit:               prep.Unit,
			Decision:           model.DecisionAllow,
			Outcome:            exec.Effect,
			Reason:             "recovered_and_applied",
			HelperName:         res.Name,
			HelperPath:         res.Path,
			HelperDigest:       res.Digest,
			ManifestGeneration: man.Generation,
			ManifestDigest:     loaded.Digest,
			LaunchSurface:      "recovery",
		}
		if err := r.Decisions.Append(rec); err != nil {
			return false, err
		}
	}

	committed := &journal.Event{
		Event:              journal.KindCommitted,
		RequestID:          prep.RequestID,
		RequestDigest:      prep.RequestDigest,
		Principal:          prep.Principal,
		Action:             prep.Action,
		Unit:               prep.Unit,
		ManifestGeneration: man.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionAllow,
		Outcome:            exec.Effect,
		Reason:             "recovered_commit",
	}
	if err := r.Journal.Emit(committed); err != nil {
		return false, err
	}
	return true, nil
}

func (r *Recoverer) recoveryDeny(prep *journal.Event, loaded model.LoadedManifest, res helper.Resolution, reason string) error {
	ev := &journal.Event{
		Event:              journal.KindRecoveryDenied,
		RequestID:          prep.RequestID,
		RequestDigest:      prep.RequestDigest,
		Principal:          prep.Principal,
		Action:             prep.Action,
		Unit:               prep.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionDeny,
		Outcome:            model.OutcomeNone,
		Reason:             reason,
	}
	if err := r.Journal.Emit(ev); err != nil {
		return err
	}
	if _, hasDecision, err := r.Decisions.FindByRequestID(prep.RequestID); err != nil {
		return err
	} else if !hasDecision {
		rec := ledger.Decision{
			Seq:                ev.EventSeq,
			RequestID:          prep.RequestID,
			RequestDigest:      prep.RequestDigest,
			Principal:          prep.Principal,
			Action:             prep.Action,
			Unit:               prep.Unit,
			Decision:           model.DecisionDeny,
			Outcome:            model.OutcomeNone,
			Reason:             reason,
			HelperName:         res.Name,
			HelperPath:         res.Path,
			HelperDigest:       res.Digest,
			ManifestGeneration: loaded.Manifest.Generation,
			ManifestDigest:     loaded.Digest,
			LaunchSurface:      "recovery",
		}
		if err := r.Decisions.Append(rec); err != nil {
			return err
		}
	}
	return nil
}
