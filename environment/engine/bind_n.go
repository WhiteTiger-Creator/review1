package engine

import (
	"blkmir/stride"
	"blkmir/store"
)

func bind_n(pipe *store.StagePipe, prb store.PrbFixture, rank int) bool {
	return stride.LatchOpen(pipe, prb, rank)
}

func BindOpen(pipe *store.StagePipe, prb store.PrbFixture, rank int) bool {
	return bind_n(pipe, prb, rank)
}
