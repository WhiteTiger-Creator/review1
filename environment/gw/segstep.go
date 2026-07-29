package gw

import (
	"qdenv/dm7"
	"qdenv/internal"
	"qdenv/internal/m7"
)

func applySeg(ctx internal.LaneCtx, st internal.Frame, tbl internal.EntityTbl) (internal.LaneCtx, internal.EntityTbl) {
	tag := m7.TagFromFrame(st)
	ctx.Tbl = tbl
	ctx, _ = dm7.ReadSeg(ctx, tag, tbl)
	return ctx, ctx.Tbl
}
