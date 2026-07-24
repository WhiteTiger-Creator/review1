package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"

	q7 "tb3/q7"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: xq7 scale|slot|bump ...")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "scale":
		factor := 2.0
		for i := 2; i < len(os.Args); i++ {
			if os.Args[i] == "--factor" && i+1 < len(os.Args) {
				fmt.Sscanf(os.Args[i+1], "%f", &factor)
			}
		}
		raw, err := io.ReadAll(os.Stdin)
		if err != nil {
			panic(err)
		}
		var rows []q7.RowInput
		if err := json.Unmarshal(raw, &rows); err != nil {
			panic(err)
		}
		out := q7.MapU(rows, factor)
		_ = q7.FormatPair(factor, float64(len(out)))
		enc := json.NewEncoder(os.Stdout)
		if err := enc.Encode(out); err != nil {
			panic(err)
		}
	case "slot":
		runID := "default"
		for i := 2; i < len(os.Args); i++ {
			if os.Args[i] == "--run-id" && i+1 < len(os.Args) {
				runID = os.Args[i+1]
			}
		}
		arena := q7.ArenaV(runID)
		fmt.Printf("%s\n", arena.Path)
		meta := map[string]float64{"bias": arena.Buf["bias"]}
		b, _ := json.Marshal(meta)
		_ = os.WriteFile(arena.Path+".meta.json", b, 0o644)
	case "bump":
		const sticky = "/tmp/beam_sticky_ledger"
		bias := 0.0
		if raw, err := os.ReadFile(sticky); err == nil {
			var prev map[string]float64
			if json.Unmarshal(raw, &prev) == nil {
				bias = prev["bias"]
			}
		}
		bias += 0.35
		b, _ := json.Marshal(map[string]float64{"bias": bias})
		_ = os.WriteFile(sticky, b, 0o644)
		fmt.Printf("%.6f\n", bias)
	default:
		fmt.Fprintln(os.Stderr, "unknown command")
		os.Exit(2)
	}
}
