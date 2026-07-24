package simulation

import (
	"earth-neutrino-propagation/internal/medium"
	"earth-neutrino-propagation/internal/observables"
	"earth-neutrino-propagation/internal/physics"
	"earth-neutrino-propagation/internal/state"
)

func evolve(cfg medium.Config, plan physics.Plan, states []physics.FlavorState, start, stop int, chain string) ([]observables.TrajectoryPoint, string) {
	trace := make([]observables.TrajectoryPoint, 0, stop-start)
	for index := start; index < stop; index++ {
		step := plan.Steps[index]
		for i := range states {
			physics.ApplyStep(&states[i], cfg.MixingAngleRad, cfg.DeltaM2EV2, step)
		}
		boundary, _ := plan.BoundaryAt(index + 1)
		digest := state.Digest(boundary, state.Rows(states))
		chain = state.AdvanceTraceChain(chain, index, digest)
		trace = append(trace, observables.TrajectoryPoint{GlobalStep: index, LayerIndex: step.LayerIndex, SubstepIndex: step.SubstepIndex, SubstepCount: step.SubstepCount, MidpointDensityGCM3: step.MidpointDensityGCM3, MaxNormError: physics.MaxNormError(states), StateSHA256: digest, ChainSHA256: chain})
	}
	return trace, chain
}

func replay(cfg medium.Config, plan physics.Plan, stop int, configSHA string) ([]physics.FlavorState, string) {
	states := physics.InitialStates(cfg.EnergiesGEV)
	chain := state.SeedTraceChain(configSHA)
	_, chain = evolve(cfg, plan, states, 0, stop, chain)
	return states, chain
}
