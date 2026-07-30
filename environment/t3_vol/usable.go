package t3_vol

import "wavellite_dc/q4"

func UsableAfterLoss(in []q4.Unit, req q4.VolReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		if u.RawTB < req.MinUsable {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
