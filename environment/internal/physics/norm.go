package physics

import "math"

func NormError(s FlavorState) float64 {
	pe := real(s.Electron)*real(s.Electron) + imag(s.Electron)*imag(s.Electron)
	pm := real(s.Muon)*real(s.Muon) + imag(s.Muon)*imag(s.Muon)
	return math.Abs(pe + pm - 1)
}

func MaxNormError(states []FlavorState) float64 {
	maxError := 0.0
	for _, state := range states {
		if value := NormError(state); value > maxError {
			maxError = value
		}
	}
	return maxError
}
