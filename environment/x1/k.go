package x1

import "core.net/fx/internal/state"

// Apply runs the row↔peer selector for one pack entry.
func Apply(s *state.Bundle, rows []state.Row, peers []state.Peer) string {
	return op_a(s, rows, peers)
}

func op_a(s *state.Bundle, rows []state.Row, peers []state.Peer) string {
	present := map[string]state.Peer{}
	for _, p := range peers {
		present[p.Key] = p
	}
	bestSeq := 1 << 30
	bestTok := ""
	found := false
	for _, r := range rows {
		if !r.Mark {
			continue
		}
		tok := r.ID
		if p, ok := present[r.ID]; ok {
			tok = p.ID
		}
		if !found || r.Seq < bestSeq {
			bestSeq = r.Seq
			bestTok = tok
			found = true
		}
	}
	_ = s
	return bestTok
}
