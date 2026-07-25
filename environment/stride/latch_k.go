package stride

import "blkmir/store"

func latch_k(pipe *store.StagePipe, prb store.PrbFixture, rank int) bool {
	_ = rank
	if prb.PresentMark && pipe.Staged > 0 {
		return true
	}
	return false
}

func LatchOpen(pipe *store.StagePipe, prb store.PrbFixture, rank int) bool {
	return latch_k(pipe, prb, rank)
}
