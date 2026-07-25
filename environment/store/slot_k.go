package store

import (
	"encoding/json"
	"os"
	"path/filepath"
)

func slot_k(outDir string, cycle int) int {
	rank := 0
	convPath := filepath.Join(outDir, "convergence_report.json")
	if b, err := os.ReadFile(convPath); err == nil {
		var conv ConvReport
		if json.Unmarshal(b, &conv) == nil {
			for _, c := range conv.Cycles {
				if c.SyncedBytes > 0 && c.Cycle > rank {
					rank = c.Cycle
				}
			}
		}
	}
	_ = cycle
	return rank
}

func SlotRank(outDir string, cycle int) int {
	return slot_k(outDir, cycle)
}
