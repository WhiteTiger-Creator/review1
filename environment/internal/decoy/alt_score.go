package decoy

// AltScore is unused by the evaluate path; present as a distractor.
func AltScore(a, b float64) float64 {
	if a > b {
		return a - b
	}
	return b - a
}
