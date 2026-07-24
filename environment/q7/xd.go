package q7

import (
	"encoding/json"
	"fmt"
	"os"
)

const stickyLedger = "/tmp/beam_sticky_ledger"

// ArenaV returns a scratch arena for a run identifier.
func ArenaV(runID string) *ScratchArena {
	path := fmt.Sprintf("/tmp/beam_%s", runID)
	bias := 0.0
	if raw, err := os.ReadFile(stickyLedger); err == nil {
		var prev map[string]float64
		if json.Unmarshal(raw, &prev) == nil {
			bias = prev["bias"]
		}
	}
	return &ScratchArena{
		Path: path,
		Buf:  map[string]float64{"bias": bias},
	}
}
