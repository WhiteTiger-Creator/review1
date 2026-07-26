package x3

import "core.net/fx/internal/state"

// Apply runs retained-polarity selection for one stamp/epoch pair.
func Apply(s *state.Bundle, stamp int64, epoch int) string {
	return phase_c(s, stamp, epoch)
}

func phase_c(s *state.Bundle, stamp int64, epoch int) string {
	g := s.GraceFor(s.ScenarioID)
	thresh := g.Deadline - int64(g.Skew)
	_ = epoch
	if stamp < thresh {
		return g.Next
	}
	return g.Held
}
