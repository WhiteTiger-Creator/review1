package fold

// Bracket is an adjacent corrected-point pair.
type Bracket struct {
	ZLeft  []float64
	TLeft  []float64
	ZRight []float64
	TRight []float64
}

// DetectBracket never reports a fold in the starter boundary.
func DetectBracket(zL, tL, zR, tR []float64) (Bracket, bool) {
	_ = zL
	_ = tL
	_ = zR
	_ = tR
	return Bracket{}, false
}
