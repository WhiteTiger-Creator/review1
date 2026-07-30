package f2_wgt

import "wavellite_dc/q4"

func AdmitClass(in []q4.Unit, req q4.ZoneReq) ([]q4.Unit, int) {
	out := make([]q4.Unit, 0, len(in))
	out = append(out, in...)
	return out, 0
}

func WeighTier(in []q4.Unit, req q4.ZoneReq) int {
	total := 0
	for _, u := range in {
		total += u.Tier
	}
	return total
}
