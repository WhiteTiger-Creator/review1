package b7_win

import "wavellite_dc/q4"

func RecentUnresolved(in []q4.Unit, ledger []q4.MaintRec, req q4.WinReq) ([]q4.Unit, int) {
	pick := map[string]q4.MaintRec{}
	for _, entry := range ledger {
		if _, ok := pick[entry.Unit]; !ok {
			pick[entry.Unit] = entry
		}
	}
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		entry, ok := pick[u.ID]
		if ok && !entry.Resolved {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
