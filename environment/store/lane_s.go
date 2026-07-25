package store

func lane_s(cat CatFixture, prb PrbFixture, lanes LaneCfg, seal int) (int, int) {
	catEpoch := cat.Epoch
	prbEpoch := prb.Epoch
	if cat.Finished && seal < prbEpoch {
		return prbEpoch, prbEpoch
	}
	if lanes.CatalogLane == lanes.ProbeLane {
		return prbEpoch, catEpoch
	}
	return catEpoch, prbEpoch
}

func LaneEpochs(cat CatFixture, prb PrbFixture, lanes LaneCfg, seal int) (int, int) {
	return lane_s(cat, prb, lanes, seal)
}
