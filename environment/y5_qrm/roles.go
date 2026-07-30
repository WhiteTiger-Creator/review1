package y5_qrm

import "wavellite_dc/q4"

func DistinctRoles(in []q4.Unit, ledger []q4.Approval, req q4.SignReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		seen := 0
		for _, entry := range ledger {
			if entry.Unit != u.ID {
				continue
			}
			seen++
		}
		if seen < req.MinRoles {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
