package observables

import "earth-neutrino-propagation/internal/state"

type FlavorOutcome struct {
	EnergyGEV float64    `json:"energy_gev"`
	Electron  [2]float64 `json:"electron"`
	Muon      [2]float64 `json:"muon"`
	PE        float64    `json:"p_e"`
	PMu       float64    `json:"p_mu"`
	NormError float64    `json:"norm_error"`
}

type TrajectoryPoint struct {
	GlobalStep          int     `json:"global_step"`
	LayerIndex          int     `json:"layer_index"`
	SubstepIndex        int     `json:"substep_index"`
	SubstepCount        int     `json:"substep_count"`
	MidpointDensityGCM3 float64 `json:"midpoint_density_g_cm3"`
	MaxNormError        float64 `json:"max_norm_error"`
	StateSHA256         string  `json:"state_sha256"`
	ChainSHA256         string  `json:"chain_sha256"`
}

type Propagation struct {
	SchemaVersion         int               `json:"schema_version"`
	ConfigSHA256          string            `json:"config_sha256"`
	StartLayer            int               `json:"start_layer"`
	StartSubstep          int               `json:"start_substep"`
	StartCompletedSteps   int               `json:"start_completed_steps"`
	EndLayer              int               `json:"end_layer"`
	EndSubstep            int               `json:"end_substep"`
	CompletedSteps        int               `json:"completed_steps"`
	CompletedLayers       int               `json:"completed_layers"`
	FinalStateSHA256      string            `json:"final_state_sha256"`
	FinalTraceChainSHA256 string            `json:"final_trace_chain_sha256"`
	Energies              []FlavorOutcome   `json:"energies"`
	Trace                 []TrajectoryPoint `json:"trace"`
}

type Reproducibility struct {
	SchemaVersion         int    `json:"schema_version"`
	ConfigSHA256          string `json:"config_sha256"`
	Mode                  string `json:"mode"`
	StartLayer            int    `json:"start_layer"`
	StartSubstep          int    `json:"start_substep"`
	StartCompletedSteps   int    `json:"start_completed_steps"`
	EndLayer              int    `json:"end_layer"`
	EndSubstep            int    `json:"end_substep"`
	CompletedSteps        int    `json:"completed_steps"`
	PropagationSHA256     string `json:"propagation_sha256"`
	ContinuationSHA256    string `json:"continuation_sha256"`
	FinalStateSHA256      string `json:"final_state_sha256"`
	FinalTraceChainSHA256 string `json:"final_trace_chain_sha256"`
}

type Bundle struct {
	Propagation     Propagation
	Continuation    state.Continuation
	Reproducibility Reproducibility
}
