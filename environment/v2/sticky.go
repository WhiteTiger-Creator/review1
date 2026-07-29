package v2

// SoftFlip toggles Gate.Soft for soft-handoff bookkeeping.
func SoftFlip(g *Gate) {
	if g == nil {
		return
	}
	g.Soft = !g.Soft
}
