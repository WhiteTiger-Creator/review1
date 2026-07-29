package engine

import (
	"blkmir/stride"
	"blkmir/store"
)

func bind_n(pipe *store.StagePipe, prb store.PrbFixture, rank int, waves store.WaveFlags) bool {
	return stride.LatchOpen(pipe, prb, rank, waves)
}

func BindOpen(pipe *store.StagePipe, prb store.PrbFixture, rank int, waves store.WaveFlags) bool {
	return bind_n(pipe, prb, rank, waves)
}
