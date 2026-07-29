package gw

import (
	"qdenv/internal"
)

const modularSpan = 65536

// RunLane executes one lane manifest through the play pipeline.
func RunLane(m internal.LaneManifest) ([]internal.TickLine, internal.EntityTbl) {
	ctx := internal.LaneCtx{}
	tbl := internal.EntityTbl{}
	var buf internal.FrameBuf
	journal := internal.Journal{}
	view := internal.View{}
	var lines []internal.TickLine
	span := internal.Span{Mod: modularSpan}

	for _, step := range m.Steps {
		steps := []internal.Frame{step}
		for r := 0; r < step.Depth%3; r++ {
			dup := step
			dup.Label = step.Label + "_r"
			steps = append(steps, dup)
		}
		for _, st := range steps {
			buf = applyGate(buf, st)
			ctx, tbl = applySeg(ctx, st, tbl)
			journal, ctx = applyResume(journal, st, ctx)
			tbl = internal.ApplySlotDelta(ctx.Tbl, st.Seq%8, st.SlotDelta)
			ctx.Tbl = tbl
			view = applyFold(view, st, span)

			bearing := int(view.Bearing) % modularSpan
			if bearing < 0 {
				bearing += modularSpan
			}
			slot := tbl.Slots[st.Seq%8] % 1000003
			segCRC := tbl.CRC()
			lines = append(lines, internal.TickLine{
				Seq:     st.Seq,
				Label:   st.Label,
				Bearing: bearing,
				SlotIdx: slot,
				SegCRC:  segCRC,
			})
		}
	}
	return lines, tbl
}
