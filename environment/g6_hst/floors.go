package g6_hst

import "wavellite_dc/q4"

func MatchFloors(in []q4.Unit, req q4.HostReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		if u.ReadyNodes < req.MinNodes {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
