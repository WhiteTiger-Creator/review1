package engine

import "blkmir/store"

func grade_u(pipe *store.StagePipe, waves store.WaveFlags, prb store.PrbFixture) *store.CordLedger {
	return store.NewCord(pipe, waves, prb)
}

func buildCord(pipe *store.StagePipe, waves store.WaveFlags, prb store.PrbFixture) *store.CordLedger {
	return grade_u(pipe, waves, prb)
}
