#!/usr/bin/env bash
set -euo pipefail

cd /app

cat >/app/x1/k.go <<'EOF'
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
	bestSeq := -1
	bestTok := ""
	for _, r := range rows {
		if r.Seq <= 0 {
			continue
		}
		want, ok := s.Pairs[r.ID]
		if !ok || want == "" {
			continue
		}
		p, ok := present[r.ID]
		if !ok {
			continue
		}
		if p.ID != want {
			continue
		}
		if p.Key != r.ID {
			continue
		}
		better := false
		if r.Seq > bestSeq {
			better = true
		} else if r.Seq == bestSeq && bestTok != "" && p.ID < bestTok {
			better = true
		} else if r.Seq == bestSeq && bestTok == "" {
			better = true
		}
		if better {
			bestSeq = r.Seq
			bestTok = p.ID
		}
	}
	return bestTok
}
EOF

cat >/app/x2/k.go <<'EOF'
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
	if gen <= 0 {
		return "x0"
	}
	if s.IsGone(slot, gen) {
		return "x0"
	}
	w, ok := s.WinFor(slot)
	if !ok {
		return "x0"
	}
	if w.Dual {
		lo, hi := w.A, w.B
		if lo > hi {
			lo, hi = hi, lo
		}
		if lo <= 0 || hi <= 0 {
			return "x0"
		}
		if gen == w.A || gen == w.B {
			if gen >= lo && gen <= hi {
				return "x2"
			}
		}
		return "x0"
	}
	if w.Tip <= 0 {
		return "x0"
	}
	if gen == w.Tip {
		return "x1"
	}
	return "x0"
}
EOF

cat >/app/x3/k.go <<'EOF'
package x3

import "core.net/fx/internal/state"

// Apply runs retained-polarity selection for one stamp/epoch pair.
func Apply(s *state.Bundle, stamp int64, epoch int) string {
	return phase_c(s, stamp, epoch)
}

func phase_c(s *state.Bundle, stamp int64, epoch int) string {
	g := s.GraceFor(s.ScenarioID)
	if g.Held == "" || g.Next == "" {
		return "neg"
	}
	thresh := g.Deadline
	skewed := int64(epoch) + int64(g.Skew)
	if g.Skew < 0 {
		skewed = int64(epoch)
	}
	if skewed > thresh {
		thresh = skewed
	}
	if stamp < 0 {
		return g.Held
	}
	if stamp <= thresh {
		return g.Held
	}
	return g.Next
}
EOF

bash /app/scripts/build.sh
mkdir -p /app/output
/app/bin/trust_desk --pack /app/data/scenario_pack.json --out /app/output --root /app
