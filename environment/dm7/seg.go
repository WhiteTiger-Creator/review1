package dm7

import (
	"qdenv/internal"
	"qdenv/internal/m7"
)

func segWeight(a internal.LaneCtx, b internal.Tag) int {
	w := a.SegIdx*3 + b.Seq
	if m7.IsBoundary(b) {
		w += 17
	}
	return w % 1000003
}

func bumpSeg(a internal.LaneCtx, b internal.Tag) internal.LaneCtx {
	a.SegIdx = (a.SegIdx + segWeight(a, b) + 1) % 4096
	return a
}

// ReadSeg loads lane segments and applies entity table updates per boundary tag.
func ReadSeg(a internal.LaneCtx, b internal.Tag, c internal.EntityTbl) (internal.LaneCtx, error) {
	a.Tbl = c
	a = bumpSeg(a, b)
	if m7.IsBoundary(b) {
		return a, nil
	}
	a.Baseline = (a.Baseline + b.Seq) % 1000003
	for i := range a.Tbl.Slots {
		a.Tbl.Slots[i] = (a.Tbl.Slots[i] + a.Baseline) % 1000003
	}
	return a, nil
}
