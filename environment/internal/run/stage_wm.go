package run

import (
	"wavellite_dc/f2_wgt"
	"wavellite_dc/q4"
	"wavellite_dc/x6_sig"
)

func stageWm(row q4.SiteRow, kept []q4.Unit, pol q4.Policy) q4.SiteRow {
	row.ReadinessIndex = f2_wgt.WeighTier(kept, q4.ZoneReq{
		Classes: pol.AllowedClasses,
		Weights: pol.RegionWeights,
	})
	row.Attestation = x6_sig.BindMark(row)
	return row
}
