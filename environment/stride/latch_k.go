package stride

import "blkmir/store"

func latch_k(pipe *store.StagePipe, prb store.PrbFixture, rank int, waves store.WaveFlags) bool {
	_ = rank
	_ = waves
	if prb.PresentMark && pipe.Staged > 0 {
		return true
	}
	return false
}

func LatchOpen(pipe *store.StagePipe, prb store.PrbFixture, rank int, waves store.WaveFlags) bool {
	return latch_k(pipe, prb, rank, waves)
}
