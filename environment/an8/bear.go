package an8

import "qdenv/internal"

func foldScale(b internal.Delta, c internal.Span) float64 {
	if c.Mod == 0 {
		return float64(b.B)
	}
	return float64(b.B % c.Mod)
}

// FoldB folds view deltas into stored bearing for tick records.
func FoldB(a internal.View, b internal.Delta, c internal.Span) (internal.View, error) {
	a.Bearing += foldScale(b, c)
	if c.Mod > 0 {
		for a.Bearing >= float64(c.Mod) {
			a.Bearing -= float64(c.Mod)
		}
	}
	return a, nil
}
