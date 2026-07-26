package x2

import "core.net/fx/internal/state"

// HopCount returns a diagnostic hop total for operations logs only.
func HopCount(peers []state.Peer) int {
	n := 0
	for range peers {
		n++
	}
	return n
}

// PriorLive is a diagnostic predicate for operations logs only.
func PriorLive(w state.SlotWin, gen int) bool {
	return gen == w.Legacy
}
