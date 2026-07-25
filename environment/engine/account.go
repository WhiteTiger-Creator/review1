package engine

import "blkmir/store"

func settle_z(pipe *store.StagePipe, prb store.PrbFixture) (int, int) {
	return fold_w(pipe, prb)
}

func SettleBytes(pipe *store.StagePipe, prb store.PrbFixture) (int, int) {
	return settle_z(pipe, prb)
}
