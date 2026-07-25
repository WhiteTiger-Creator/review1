package view

import "core.net/fx/internal/state"

// SignerPick selects a row id using mark bits only (signer-view path).
func SignerPick(rows []state.Row) string {
	for _, r := range rows {
		if r.Mark {
			return r.ID
		}
	}
	return ""
}

// AcceptsProbe is true when the corpus row claims probe_ok.
func AcceptsProbe(s *state.Bundle, id string) bool {
	ce, ok := s.Corpus[id]
	return ok && ce.ProbeOK
}
