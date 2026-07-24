// Package dispatch implements the privileged dispatcher control flow:
// authorization before execution, durable journaling in a fixed order, exact
// retry idempotency, and body-substitution conflict detection.
package dispatch

import (
	"fmt"
	"os"

	"privhelper/internal/canonical"
	"privhelper/internal/helper"
	"privhelper/internal/journal"
	"privhelper/internal/ledger"
	"privhelper/internal/manifest"
	"privhelper/internal/model"
	"privhelper/internal/policy"
)

// Crash points controllable via --crash-after.
const (
	CrashNone     = ""
	CrashPrepared = "prepared"
	CrashEffect   = "effect"
)

// Dispatcher wires together the manifest, journal, and ledgers.
type Dispatcher struct {
	Paths     model.Paths
	Manifests *manifest.Store
	Journal   *journal.Store
	Decisions *ledger.DecisionStore
	Effects   *ledger.EffectStore
}

// New builds a Dispatcher for the given layout.
func New(p model.Paths) *Dispatcher {
	return &Dispatcher{
		Paths:     p,
		Manifests: manifest.NewStore(p),
		Journal:   journal.NewStore(p),
		Decisions: ledger.NewDecisionStore(p),
		Effects:   ledger.NewEffectStore(p),
	}
}

// SetTrace configures a per-run trace file mirror for journal events.
func (d *Dispatcher) SetTrace(path string) {
	if path == "" {
		d.Journal.Trace = nil
		return
	}
	d.Journal.Trace = &journal.Trace{Path: path}
}

// Dispatch evaluates a single request and returns the recorded decision.
func (d *Dispatcher) Dispatch(req model.Request, launchSurface, crashAfter string) (ledger.Decision, error) {
	if err := canonical.ValidateRequest(req); err != nil {
		return ledger.Decision{}, err
	}
	digest := canonical.Digest(req)

	loaded, err := d.Manifests.LoadCurrent()
	if err != nil {
		// A missing or unverifiable manifest means we have no authority: deny.
		return d.denyWithoutManifest(req, digest, launchSurface, err)
	}
	man := loaded.Manifest

	// Resolve helper identity up front so every record carries the trusted
	// helper it would have used.
	res := helper.ResolveByAction(d.Paths, man, req.Action)

	base := ledger.Decision{
		RequestID:          req.RequestID,
		RequestDigest:      digest,
		Principal:          req.Principal,
		Action:             req.Action,
		Unit:               req.Unit,
		HelperName:         res.Name,
		HelperPath:         res.Path,
		HelperDigest:       res.Digest,
		ManifestGeneration: man.Generation,
		ManifestDigest:     loaded.Digest,
		LaunchSurface:      launchSurface,
	}

	// Exact retry / body substitution handling against prior committed history.
	prior, hasPrior, err := d.Decisions.FindByRequestID(req.RequestID)
	if err != nil {
		return ledger.Decision{}, err
	}
	if hasPrior {
		if prior.RequestDigest == digest {
			// Exact retry: return the prior committed decision, no new effect.
			return prior, nil
		}
		// Same request_id, different body: a substitution attempt. Deny with a
		// conflict decision and journal a conflict event; no effect.
		return d.recordConflict(base, loaded, res)
	}

	auth := policy.Authorize(man, req.Principal, req.Action)
	if !auth.Authorized {
		return d.recordDeny(base, loaded, res, auth.Reason)
	}
	if !res.Trusted {
		// Authorized by policy, but the helper artifact is not trustworthy:
		// deny and never execute.
		return d.recordDeny(base, loaded, res, res.Reason)
	}

	return d.recordAllow(req, base, loaded, res, launchSurface, crashAfter)
}

func (d *Dispatcher) denyWithoutManifest(req model.Request, digest, launchSurface string, cause error) (ledger.Decision, error) {
	rec := ledger.Decision{
		RequestID:     req.RequestID,
		RequestDigest: digest,
		Principal:     req.Principal,
		Action:        req.Action,
		Unit:          req.Unit,
		Decision:      model.DecisionDeny,
		Outcome:       model.OutcomeNone,
		Reason:        fmt.Sprintf("manifest_unavailable: %v", cause),
		LaunchSurface: launchSurface,
	}
	ev := &journal.Event{
		Event:         journal.KindDenied,
		RequestID:     req.RequestID,
		RequestDigest: digest,
		Principal:     req.Principal,
		Action:        req.Action,
		Unit:          req.Unit,
		Decision:      model.DecisionDeny,
		Outcome:       model.OutcomeNone,
		Reason:        rec.Reason,
	}
	if err := d.Journal.Emit(ev); err != nil {
		return ledger.Decision{}, err
	}
	rec.Seq = ev.EventSeq
	if err := d.Decisions.Append(rec); err != nil {
		return ledger.Decision{}, err
	}
	return rec, nil
}

func (d *Dispatcher) recordDeny(base ledger.Decision, loaded model.LoadedManifest, res helper.Resolution, reason string) (ledger.Decision, error) {
	rec := base
	rec.Decision = model.DecisionDeny
	rec.Outcome = model.OutcomeNone
	rec.Reason = reason

	ev := &journal.Event{
		Event:              journal.KindDenied,
		RequestID:          base.RequestID,
		RequestDigest:      base.RequestDigest,
		Principal:          base.Principal,
		Action:             base.Action,
		Unit:               base.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionDeny,
		Outcome:            model.OutcomeNone,
		Reason:             reason,
	}
	if err := d.Journal.Emit(ev); err != nil {
		return ledger.Decision{}, err
	}
	rec.Seq = ev.EventSeq
	if err := d.Decisions.Append(rec); err != nil {
		return ledger.Decision{}, err
	}
	return rec, nil
}

func (d *Dispatcher) recordConflict(base ledger.Decision, loaded model.LoadedManifest, res helper.Resolution) (ledger.Decision, error) {
	rec := base
	rec.Decision = model.DecisionConflict
	rec.Outcome = model.OutcomeNone
	rec.Reason = "request_id_body_substitution"

	ev := &journal.Event{
		Event:              journal.KindConflict,
		RequestID:          base.RequestID,
		RequestDigest:      base.RequestDigest,
		Principal:          base.Principal,
		Action:             base.Action,
		Unit:               base.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionConflict,
		Outcome:            model.OutcomeNone,
		Reason:             rec.Reason,
	}
	if err := d.Journal.Emit(ev); err != nil {
		return ledger.Decision{}, err
	}
	rec.Seq = ev.EventSeq
	if err := d.Decisions.Append(rec); err != nil {
		return ledger.Decision{}, err
	}
	return rec, nil
}

func (d *Dispatcher) recordAllow(req model.Request, base ledger.Decision, loaded model.LoadedManifest, res helper.Resolution, launchSurface, crashAfter string) (ledger.Decision, error) {
	binding := model.Binding{
		RequestDigest:      base.RequestDigest,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
	}

	// 1. prepared (sync)
	prepared := &journal.Event{
		Event:              journal.KindPrepared,
		RequestID:          base.RequestID,
		RequestDigest:      base.RequestDigest,
		Principal:          base.Principal,
		Action:             base.Action,
		Unit:               base.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionAllow,
		Reason:             "authorized_prepared",
	}
	if err := d.Journal.Emit(prepared); err != nil {
		return ledger.Decision{}, err
	}
	if crashAfter == CrashPrepared {
		os.Exit(1)
	}

	// 2. execute helper (using verified bytes only)
	exec, err := helper.Execute(res, req, binding)
	if err != nil {
		// Execution failed after prepare: deny with no effect.
		return d.recordDeny(base, loaded, res, fmt.Sprintf("helper_execution_failed: %v", err))
	}

	// 3. write effect row (sync)
	effect := ledger.Effect{
		Seq:                prepared.EventSeq,
		RequestID:          base.RequestID,
		RequestDigest:      base.RequestDigest,
		Principal:          base.Principal,
		Action:             base.Action,
		Unit:               base.Unit,
		Effect:             exec.Effect,
		HelperName:         res.Name,
		HelperPath:         res.Path,
		HelperDigest:       res.Digest,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
	}
	if err := d.Effects.Append(effect); err != nil {
		return ledger.Decision{}, err
	}

	// 4. effect_applied (sync)
	applied := &journal.Event{
		Event:              journal.KindEffectApplied,
		RequestID:          base.RequestID,
		RequestDigest:      base.RequestDigest,
		Principal:          base.Principal,
		Action:             base.Action,
		Unit:               base.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Outcome:            exec.Effect,
		Reason:             "effect_applied",
	}
	if err := d.Journal.Emit(applied); err != nil {
		return ledger.Decision{}, err
	}
	if crashAfter == CrashEffect {
		os.Exit(1)
	}

	// 5. write decision (sync)
	rec := base
	rec.Seq = prepared.EventSeq
	rec.Decision = model.DecisionAllow
	rec.Outcome = exec.Effect
	rec.Reason = "authorized_and_applied"
	if err := d.Decisions.Append(rec); err != nil {
		return ledger.Decision{}, err
	}

	// 6. committed (sync)
	committed := &journal.Event{
		Event:              journal.KindCommitted,
		RequestID:          base.RequestID,
		RequestDigest:      base.RequestDigest,
		Principal:          base.Principal,
		Action:             base.Action,
		Unit:               base.Unit,
		ManifestGeneration: loaded.Manifest.Generation,
		ManifestDigest:     loaded.Digest,
		HelperName:         res.Name,
		HelperDigest:       res.Digest,
		Decision:           model.DecisionAllow,
		Outcome:            exec.Effect,
		Reason:             "committed",
	}
	if err := d.Journal.Emit(committed); err != nil {
		return ledger.Decision{}, err
	}
	return rec, nil
}
