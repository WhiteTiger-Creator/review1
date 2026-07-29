package engine

import "blkmir/store"

type settleView struct {
	debtOpen bool
	axisOpen bool
}

func viewFrom(prb store.PrbFixture) settleView {
	return settleView{
		debtOpen: prb.HoleDebt > 0,
		axisOpen: !prb.HolesCleared || !prb.ContentCaught,
	}
}

func fold_w(pipe *store.StagePipe, prb store.PrbFixture, waves store.WaveFlags, cord *store.CordLedger) (int, int) {
	return SettlePhased(pipe, prb, waves, cord)
}

func settle_z(pipe *store.StagePipe, prb store.PrbFixture, waves store.WaveFlags, cord *store.CordLedger) (int, int) {
	_ = viewFrom(prb)
	return fold_w(pipe, prb, waves, cord)
}
