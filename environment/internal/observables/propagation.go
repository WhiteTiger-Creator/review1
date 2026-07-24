package observables

import (
	"math"

	"earth-neutrino-propagation/internal/physics"
)

func FlavorOutcomes(states []physics.FlavorState) []FlavorOutcome {
	rows := make([]FlavorOutcome, len(states))
	for i, state := range states {
		pe := real(state.Electron)*real(state.Electron) + imag(state.Electron)*imag(state.Electron)
		pm := real(state.Muon)*real(state.Muon) + imag(state.Muon)*imag(state.Muon)
		rows[i] = FlavorOutcome{EnergyGEV: state.EnergyGEV, Electron: [2]float64{real(state.Electron), imag(state.Electron)}, Muon: [2]float64{real(state.Muon), imag(state.Muon)}, PE: pe, PMu: pm, NormError: math.Abs(pe + pm - 1)}
	}
	return rows
}
