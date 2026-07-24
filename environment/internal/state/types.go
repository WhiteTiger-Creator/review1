package state

type Amplitude struct {
	EnergyGEV float64    `json:"energy_gev"`
	Electron  [2]float64 `json:"electron"`
	Muon      [2]float64 `json:"muon"`
}

type Continuation struct {
	SchemaVersion    int         `json:"schema_version"`
	ConfigSHA256     string      `json:"config_sha256"`
	NextLayer        int         `json:"next_layer"`
	NextSubstep      int         `json:"next_substep"`
	CompletedSteps   int         `json:"completed_steps"`
	Amplitudes       []Amplitude `json:"amplitudes"`
	StateSHA256      string      `json:"state_sha256"`
	TraceChainSHA256 string      `json:"trace_chain_sha256"`
}
