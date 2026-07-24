package physics

type FlavorState struct {
	EnergyGEV float64
	Electron  complex128
	Muon      complex128
}

func InitialStates(energies []float64) []FlavorState {
	states := make([]FlavorState, len(energies))
	for i, energy := range energies {
		states[i] = FlavorState{EnergyGEV: energy, Electron: 1}
	}
	return states
}

func CloneStates(states []FlavorState) []FlavorState {
	return append([]FlavorState(nil), states...)
}
