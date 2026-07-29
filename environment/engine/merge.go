package engine

import (
	"path/filepath"

	"blkmir/stride"
	"blkmir/store"
)

func catFixture(cycle int) string {
	if cycle == 1 {
		return "catalog_view_a.json"
	}
	return "catalog_view_b.json"
}

func prbFixture(cycle int) string {
	if cycle == 1 {
		return "probe_view_a.json"
	}
	return "probe_view_b.json"
}

func pulse_y(ioDone bool, holdUS int) int {
	if holdUS > 0 {
		return holdUS / 1000
	}
	return 0
}

func packedBaseline(ctx *store.RunCtx, cat store.CatFixture, prb store.PrbFixture) (int, int) {
	if ctx != nil && ctx.Append && ctx.OutDir != "" {
		return rebase_v(ctx.OutDir, ctx.Cycle, cat, prb)
	}
	_, _ = store.BundleEpochs(cat, prb)
	return cat.Epoch - 1, cat.Epoch - 1
}

func diffSegments(ctx *store.RunCtx, root string, cycle int) ([]store.SegmentRow, error) {
	var cat store.CatFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", catFixture(cycle)), &cat); err != nil {
		return nil, err
	}
	var prb store.PrbFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", prbFixture(cycle)), &prb); err != nil {
		return nil, err
	}
	aBase, bBase := packedBaseline(ctx, cat, prb)
	rows := []store.SegmentRow{
		{LegID: "leg-a", ByteOffset: 0, Epoch: aBase},
		{
			LegID:      "leg-b",
			ByteOffset: prb.DelayedOffset,
			HoldMS:     0,
			Epoch:      bBase,
			IODone:     prb.LegBIODone,
		},
	}
	return rows, nil
}

func mergeSegments(ctx *store.RunCtx, root string, cycle int, holdUS int) ([]store.SegmentRow, error) {
	priorRows, err := diffSegments(ctx, root, cycle)
	if err != nil {
		return nil, err
	}
	var out []store.SegmentRow
	for i, prior := range priorRows {
		next := prior
		var prb store.PrbFixture
		_ = store.ReadJSON(filepath.Join(root, "fixtures", prbFixture(cycle)), &prb)
		if i == 0 {
			next.IODone = prb.LegAIODone
		}
		if i == 1 {
			next.LegID = "leg-b"
			next.ByteOffset = prior.ByteOffset
			next.IODone = prb.LegBIODone
			next.HoldMS = pulse_y(prb.LegBIODone, holdUS)
		}
		row, err := stride.NudgeSeg(ctx, prior, next)
		if err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, nil
}
