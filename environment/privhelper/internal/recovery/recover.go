// Package recovery reconstructs dispatcher state from the durable journal after
// a crash.
package recovery

import (
	"fmt"

	"privhelper/internal/helper"
	"privhelper/internal/journal"
	"privhelper/internal/ledger"
	"privhelper/internal/manifest"
	"privhelper/internal/model"
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

// Run performs one recovery pass.
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
			continue
		}
		if st.committed {
			sum.AlreadyDone++
			continue
		}
		sum.PendingFound++

		sum.Reevaluated++
		completed, err := r.resumePrepared(st)
		if err != nil {
			return sum, err
		}
		if completed {
			sum.Completed++
			sum.Committed++
		} else {
			sum.Denied++
		}
	}

	return sum, nil
}

func (r *Recoverer) resumePrepared(st *reqState) (bool, error) {
	prep := st.prepared

	loaded, err := r.Manifests.LoadCurrent()
	if err != nil {
		return false, r.recoveryDeny(prep, model.LoadedManifest{}, helper.Resolution{}, fmt.Sprintf("manifest_unavailable_during_recovery: %v", err))
	}

	man := loaded.Manifest
	res := helper.ResolveByAction(r.Paths, man, prep.Action)
	req := model.Request{
		RequestID: prep.RequestID,
		Principal: prep.Principal,
		Action:    prep.Action,
		Unit:      prep.Unit,
	}
	binding := model.Binding{
		RequestDigest:      prep.RequestDigest,
		ManifestGeneration: prep.ManifestGeneration,
		ManifestDigest:     prep.ManifestDigest,
	}

	exec, err := helper.Execute(res, req, binding)
	if err != nil {
		return false, r.recoveryDeny(prep, loaded, res, fmt.Sprintf("helper_execution_failed_on_recovery: %v", err))
	}

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
		ManifestGeneration: prep.ManifestGeneration,
		ManifestDigest:     prep.ManifestDigest,
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
		ManifestGeneration: prep.ManifestGeneration,
		ManifestDigest:     prep.ManifestDigest,
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
			ManifestGeneration: prep.ManifestGeneration,
			ManifestDigest:     prep.ManifestDigest,
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
		ManifestGeneration: prep.ManifestGeneration,
		ManifestDigest:     prep.ManifestDigest,
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
