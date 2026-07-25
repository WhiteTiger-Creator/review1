package x1

import "core.net/fx/internal/state"

// RankRows orders rows by seq for probe display only.
func RankRows(rows []state.Row) []state.Row {
	out := append([]state.Row(nil), rows...)
	for i := 0; i < len(out); i++ {
		for j := i + 1; j < len(out); j++ {
			if out[j].Seq > out[i].Seq {
				out[i], out[j] = out[j], out[i]
			}
		}
	}
	return out
}

// PickMarked returns the first marked row id for signer-view summaries.
func PickMarked(rows []state.Row) string {
	for _, r := range RankRows(rows) {
		if r.Mark {
			return r.ID
		}
	}
	if len(rows) == 0 {
		return ""
	}
	return rows[0].ID
}
