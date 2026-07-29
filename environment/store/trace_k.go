package store

import (
	"encoding/json"
	"os"
	"strings"
)

func trace_k(outDir string, cycle int) bool {
	path := outDir + "/progress_trace.jsonl"
	b, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	for _, line := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		if line == "" {
			continue
		}
		var row TraceLine
		if json.Unmarshal([]byte(line), &row) != nil {
			continue
		}
		if row.Epoch == cycle && row.Op == "latch" {
			return true
		}
	}
	return false
}

func TraceLatchSealed(outDir string, cycle int) bool {
	return trace_k(outDir, cycle)
}
