package gw

import (
	"qdenv/an8"
	"qdenv/internal"
)

func applyFold(view internal.View, st internal.Frame, span internal.Span) internal.View {
	delta := internal.Delta{B: st.BearingDelta + internal.LabelWeight(st.Label)}
	view, _ = an8.FoldB(view, delta, span)
	return view
}
