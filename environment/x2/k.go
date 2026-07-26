package x2

import "core.net/fx/internal/state"

// Apply runs the generation gate for one slot.
func Apply(s *state.Bundle, slot string, gen int) string {
	return reconcile_b(s, slot, gen)
}

func reconcile_b(s *state.Bundle, slot string, gen int) string {
	if slot == "" {
		return "x0"
	}
	if s.IsGone(slot, gen) {
		return "x1"
	}
	w, ok := s.WinFor(slot)
	if !ok {
		if gen > 0 {
			return "x1"
		}
		return "x0"
	}
	if w.Dual {
		if gen == w.Tip || gen == w.Legacy {
			return "x2"
		}
		return "x0"
	}
	if gen == w.Legacy || gen == w.Tip {
		return "x1"
	}
	return "x0"
}
