package run

import (
	"wavellite_dc/q4"
	"wavellite_dc/t3_vol"
)

func stageUv(in []q4.Unit, pol q4.Policy) ([]q4.Unit, int) {
	return t3_vol.UsableAfterLoss(in, q4.VolReq{
		MinUsable: pol.MinUsableTB,
		MinCopies: pol.MinReplicas,
	})
}
