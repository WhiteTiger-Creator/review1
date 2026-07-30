package w9_lnk

import "wavellite_dc/q4"

func RequirePair(in []q4.Unit, req q4.LinkReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		live := false
		for _, path := range u.Uplinks {
			if path.Healthy {
				live = true
				break
			}
		}
		if !live {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
