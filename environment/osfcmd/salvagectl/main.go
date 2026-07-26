package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"orbsalvage/osflib/sortie"
)

type roster struct {
	Sorties []string `json:"sorties"`
}

func main() {
	deckDir := "/app/sortie_deck"
	rosterPath := filepath.Join(deckDir, "roster.json")
	outPath := "/app/build/fleet_sortie_ledger.json"

	raw, err := os.ReadFile(rosterPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read roster: %v\n", err)
		os.Exit(1)
	}
	var ros roster
	if err := json.Unmarshal(raw, &ros); err != nil {
		fmt.Fprintf(os.Stderr, "parse roster: %v\n", err)
		os.Exit(1)
	}

	report := sortie.Report{Sorties: make([]sortie.SortieOut, 0, len(ros.Sorties))}
	for _, id := range ros.Sorties {
		path := filepath.Join(deckDir, id+".json")
		m, err := sortie.LoadMission(path)
		if err != nil {
			fmt.Fprintf(os.Stderr, "load %s: %v\n", path, err)
			os.Exit(1)
		}
		report.Sorties = append(report.Sorties, sortie.Analyze(m))
	}

	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir: %v\n", err)
		os.Exit(1)
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(report); err != nil {
		fmt.Fprintf(os.Stderr, "marshal: %v\n", err)
		os.Exit(1)
	}
	if err := os.WriteFile(outPath, buf.Bytes(), 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write: %v\n", err)
		os.Exit(1)
	}
}
