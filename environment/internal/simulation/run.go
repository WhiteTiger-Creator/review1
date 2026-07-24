package simulation

import (
	"errors"
	"fmt"

	"earth-neutrino-propagation/internal/medium"
	"earth-neutrino-propagation/internal/observables"
	"earth-neutrino-propagation/internal/physics"
	"earth-neutrino-propagation/internal/state"
)

func Run(opts Options) error {
	cfg, _, configSHA, err := medium.Load(opts.ConfigPath)
	if err != nil {
		return err
	}
	plan := physics.BuildPlan(cfg)
	startBoundary, _ := plan.BoundaryAt(0)
	states := physics.InitialStates(cfg.EnergiesGEV)
	chain := state.SeedTraceChain(configSHA)
	mode := "fresh"
	if opts.ResumePath != "" {
		cp, restored, err := state.Load(opts.ResumePath, configSHA, plan, cfg.EnergiesGEV)
		if err != nil {
			return err
		}
		startBoundary = physics.Boundary{NextLayer: cp.NextLayer, NextSubstep: cp.NextSubstep, CompletedSteps: cp.CompletedSteps}
		replayed, replayChain := replay(cfg, plan, cp.CompletedSteps, configSHA)
		if !state.EqualStates(restored, replayed, 2e-12) || replayChain != cp.TraceChainSHA256 {
			return errors.New("invalid continuation history")
		}
		startBoundary.CompletedSteps++
		states, chain, mode = restored, cp.TraceChainSHA256, "resume"
	}
	stop, err := resolveStop(opts, plan)
	if err != nil {
		return err
	}
	if stop < startBoundary.CompletedSteps {
		return errors.New("invalid stop boundary before resume point")
	}
	trace, chain := evolve(cfg, plan, states, startBoundary.CompletedSteps, stop, chain)
	endBoundary, _ := plan.BoundaryAt(stop)
	cp := state.FromStates(configSHA, endBoundary, chain, states)
	propagation := observables.Propagation{
		SchemaVersion: 2, ConfigSHA256: configSHA,
		StartLayer: startBoundary.NextLayer, StartSubstep: startBoundary.NextSubstep, StartCompletedSteps: startBoundary.CompletedSteps,
		EndLayer: endBoundary.NextLayer, EndSubstep: endBoundary.NextSubstep, CompletedSteps: endBoundary.CompletedSteps, CompletedLayers: endBoundary.NextLayer,
		FinalStateSHA256: cp.StateSHA256, FinalTraceChainSHA256: chain, Energies: observables.FlavorOutcomes(states), Trace: trace,
	}
	propagationBytes, err := observables.JSON(propagation)
	if err != nil {
		return fmt.Errorf("encode propagation: %w", err)
	}
	continuationBytes, err := observables.JSON(cp)
	if err != nil {
		return fmt.Errorf("encode continuation: %w", err)
	}
	reproducibility := observables.BuildReproducibility(configSHA, mode, startBoundary, endBoundary, propagationBytes, continuationBytes, cp.StateSHA256, chain)
	reproducibilityBytes, err := observables.JSON(reproducibility)
	if err != nil {
		return fmt.Errorf("encode reproducibility: %w", err)
	}
	return observables.WritePublication([]observables.OutputFile{{Path: opts.PropagationPath, Data: propagationBytes}, {Path: opts.ContinuationPath, Data: continuationBytes}, {Path: opts.ReproducibilityPath, Data: reproducibilityBytes}})
}

func resolveStop(opts Options, plan physics.Plan) (int, error) {
	if opts.StopAfterLayers >= 0 && opts.StopAfterSteps >= 0 {
		return 0, errors.New("stop-after and stop-after-steps are mutually exclusive")
	}
	if opts.StopAfterSteps >= 0 {
		if opts.StopAfterSteps > plan.TotalSteps() {
			return 0, errors.New("invalid stop-after-steps boundary")
		}
		return opts.StopAfterSteps, nil
	}
	if opts.StopAfterLayers >= 0 {
		return plan.StepsAfterLayers(opts.StopAfterLayers)
	}
	return plan.TotalSteps(), nil
}
