package decoy

// HintNoise is a non-fix helper that looks structurally similar to scoring helpers.
func HintNoise(xs []float64) float64 {
	s := 0.0
	for _, x := range xs {
		s += x * 0.01
	}
	return s
}
