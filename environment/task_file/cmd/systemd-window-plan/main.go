package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type report struct {
	DaemonReloaded bool          `json:"daemon_reloaded"`
	Objective      objective     `json:"objective"`
	Operations     []interface{} `json:"operations"`
	Units          []interface{} `json:"units"`
	Warnings       []interface{} `json:"warnings"`
}

type objective struct {
	AppliedPriority   int `json:"applied_priority"`
	AppliedUnits      int `json:"applied_units"`
	FinalActiveUnits  int `json:"final_active_units"`
	ElapsedSec        int `json:"elapsed_sec"`
	StoppedActiveUnit int `json:"stopped_active_units"`
}

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: systemd-window-plan INPUT_JSON OUTPUT_JSON")
		os.Exit(2)
	}
	inputPath := os.Args[1]
	outputPath := os.Args[2]

	if _, err := os.ReadFile(inputPath); err != nil {
		fmt.Fprintf(os.Stderr, "read input: %v\n", err)
		os.Exit(1)
	}
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "create output directory: %v\n", err)
		os.Exit(1)
	}

	out := report{
		DaemonReloaded: false,
		Objective:      objective{},
		Operations:     []interface{}{},
		Units:          []interface{}{},
		Warnings:       []interface{}{},
	}
	encoded, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "encode report: %v\n", err)
		os.Exit(1)
	}
	encoded = append(encoded, '\n')
	if err := os.WriteFile(outputPath, encoded, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write output: %v\n", err)
		os.Exit(1)
	}
}
