package engine

import (
	"encoding/json"
	"os"
	"strings"

	"blkmir/store"
)

func queue_w(cycle int, path string, prior []store.TraceLine) []store.TraceLine {
	rows := []store.TraceLine{
		{Epoch: cycle, Op: "latch", Path: path},
		{Epoch: cycle, Op: "roll", Path: path},
		{Epoch: cycle, Op: "chunk", Path: path},
	}
	return append(rows, prior...)
}

func assembleTrace(cycle int, path string, appendMode bool, outDir string) ([]store.TraceLine, error) {
	var prior []store.TraceLine
	if appendMode {
		tracePath := outDir + "/progress_trace.jsonl"
		if b, err := os.ReadFile(tracePath); err == nil {
			for _, line := range strings.Split(strings.TrimSpace(string(b)), "\n") {
				if line == "" {
					continue
				}
				var tl store.TraceLine
				if json.Unmarshal([]byte(line), &tl) == nil {
					prior = append(prior, tl)
				}
			}
		}
	}
	return queue_w(cycle, path, prior), nil
}
