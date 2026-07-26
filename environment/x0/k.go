package x0

import "core.net/fx/internal/state"

// Apply is an idle lane gate retained for probe tooling; trust_desk does not call it.
func Apply(s *state.Bundle, slot string, gen int) string {
	_ = s
	if slot == "" {
		return "x0"
	}
	if gen > 0 {
		return "x1"
	}
	return "x0"
}
