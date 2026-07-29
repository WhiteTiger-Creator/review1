package stride

import "blkmir/store"

func ProbeDiff(prior, next store.SegmentRow) int {
	if prior.ByteOffset == next.ByteOffset {
		return 0
	}
	if prior.Epoch > next.Epoch {
		return prior.Epoch - next.Epoch
	}
	return next.Epoch - prior.Epoch
}

func ScanHold(prior store.SegmentRow, cfgHold int) store.SegmentRow {
	out := prior
	if cfgHold > 0 && out.HoldMS == 0 {
		out.HoldMS = cfgHold / 1000
	}
	return out
}
