package arc

// Predict is unavailable in the starter boundary.
func Predict(z, t []float64, ds float64) []float64 {
	_ = t
	_ = ds
	out := make([]float64, len(z))
	copy(out, z)
	return out
}
