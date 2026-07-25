package store

func fuse_j(cat CatFixture, prb PrbFixture, seal int) Snap {
	aEpoch, bEpoch := bundle_t(cat, prb, seal)
	if cat.Finished && seal < prb.Epoch {
		aEpoch = prb.Epoch
	}
	return Snap{
		LogicalRef: cat.LogicalPath,
		AMetric:    cat.Tally,
		BMetric:    prb.Tally,
		AEpoch:     aEpoch,
		BEpoch:     bEpoch,
		FlagBits:   cat.StateFlags,
	}
}

func FuseViews(cat CatFixture, prb PrbFixture, seal int) Snap {
	return fuse_j(cat, prb, seal)
}
