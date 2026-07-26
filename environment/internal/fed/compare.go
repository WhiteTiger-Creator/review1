package fed

import (
	"core.net/fx/internal/state"
	"core.net/fx/x1"
	"core.net/fx/x2"
)

// Resolve evaluates one pack entry and returns the submission token plus live mark.
func Resolve(s *state.Bundle, id string) (string, string) {
	s.ScenarioID = id
	rows := s.RowsFor(id)
	peers := s.PeersFor(id)
	tok := x1.Apply(s, rows, peers)
	gen := s.GenFor(id)
	live := x2.Apply(s, tok, gen)
	return tok, live
}

// MirrorResolve is retained for operations tooling; it is not used by trust_desk.
func MirrorResolve(s *state.Bundle, id string) (string, string) {
	rows := s.RowsFor(id)
	for _, r := range rows {
		if r.Mark {
			return r.ID, "x1"
		}
	}
	return "", "x0"
}
