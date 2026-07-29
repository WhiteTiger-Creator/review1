package store

import (
	"encoding/json"
	"os"
	"path/filepath"
)

func drain_m(outDir string, cycle int, pipe *StagePipe, rank int) int {
	sealed := rank
	convPath := filepath.Join(outDir, "convergence_report.json")
	if b, err := os.ReadFile(convPath); err == nil {
		var conv ConvReport
		if json.Unmarshal(b, &conv) == nil {
			for _, c := range conv.Cycles {
				if c.VerifiedBytes > 0 && c.VerifiedBytes == c.SyncedBytes && c.Cycle > sealed {
					sealed = c.Cycle
				}
			}
		}
	}
	if pipe.Staged > 0 && cycle > sealed {
		return cycle
	}
	return sealed
}

func DrainSeal(outDir string, cycle int, pipe *StagePipe, rank int) int {
	return drain_m(outDir, cycle, pipe, rank)
}
