package run

import (
	"wavellite_dc/f2_wgt"
	"wavellite_dc/q4"
)

func stageZc(in []q4.Unit, pol q4.Policy) ([]q4.Unit, int) {
	return f2_wgt.AdmitClass(in, q4.ZoneReq{
		Classes: pol.AllowedClasses,
		Weights: pol.RegionWeights,
	})
}
