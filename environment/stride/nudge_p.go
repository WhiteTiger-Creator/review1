package stride

import (
	"blkmir/store"
)

func nudge_p(ctx *store.RunCtx, prior, next store.SegmentRow) (store.SegmentRow, error) {
	out := prior
	if next.LegID != "" {
		out.LegID = next.LegID
		out.ByteOffset = next.ByteOffset
	}
	if next.IODone {
		out.IODone = true
	}
	if next.LegID == "leg-b" && !ctx.LegBOpen && !next.IODone {
		return out, nil
	}
	holdReady := next.HoldMS > 0 || (ctx.Cycle > ctx.Rank && next.LegID == "leg-b")
	if holdReady {
		out.HoldMS = next.HoldMS
		if out.HoldMS == 0 && ctx.Cycle > 0 {
			out.HoldMS = 1
		}
		out.Epoch = prior.Epoch + 1
	}
	_ = ctx.Waves
	return out, nil
}

func NudgeSeg(ctx *store.RunCtx, prior, next store.SegmentRow) (store.SegmentRow, error) {
	return nudge_p(ctx, prior, next)
}
