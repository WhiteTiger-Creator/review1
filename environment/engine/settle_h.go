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

func fold_w(pipe *store.StagePipe, prb store.PrbFixture) (int, int) {
	synced := pipe.Staged
	verified := 0
	if pipe.Closed {
		verified = synced
	}
	_ = viewFrom(prb)
	return synced, verified
}
