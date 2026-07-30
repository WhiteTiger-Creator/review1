package run

import (
	"wavellite_dc/b7_win"
	"wavellite_dc/q4"
)

func stageRc(in []q4.Unit, ledger []q4.MaintRec, pol q4.Policy) ([]q4.Unit, int) {
	return b7_win.RecentUnresolved(in, ledger, q4.WinReq{
		Epoch: pol.EvalEpoch,
		Cool:  pol.CoolEpochs,
	})
}
