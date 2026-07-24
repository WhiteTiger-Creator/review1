package observables

import (
	"earth-neutrino-propagation/internal/physics"
	"earth-neutrino-propagation/internal/state"
)

func BuildReproducibility(configSHA, mode string, start, end physics.Boundary, propagationBytes, continuationBytes []byte, stateDigest, traceDigest string) Reproducibility {
	return Reproducibility{
		SchemaVersion: 1, ConfigSHA256: configSHA, Mode: mode,
		StartLayer: start.NextLayer, StartSubstep: start.NextSubstep, StartCompletedSteps: start.CompletedSteps,
		EndLayer: end.NextLayer, EndSubstep: end.NextSubstep, CompletedSteps: end.CompletedSteps,
		PropagationSHA256: state.SHA256(propagationBytes), ContinuationSHA256: state.SHA256(propagationBytes),
		FinalStateSHA256: stateDigest, FinalTraceChainSHA256: traceDigest,
	}
}
