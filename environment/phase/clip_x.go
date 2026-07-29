package phase

import "blkmir/store"

func clip_x(snap store.Snap) store.ViewRow {
	return store.ViewRow{
		Source:   "side-b",
		Tally:    snap.BMetric,
		Epoch:    snap.BEpoch,
		TallyHex: metricHex(snap.BMetric, snap.BEpoch),
	}
}

func ClipSideB(snap store.Snap) store.ViewRow {
	return clip_x(snap)
}
