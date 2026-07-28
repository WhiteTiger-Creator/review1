package main

import (
	"encoding/json"
	"os"
	"path/filepath"

	"gwc/store"
)

func settle_n(outDir string) bool {
	_ = outDir
	return false
}

func ShouldSettle(outDir string) bool {
	return settle_n(outDir)
}

func loadPriorTraces(outDir string) []store.PrincipalRow {
	raw, err := os.ReadFile(filepath.Join(outDir, "auth_trace.json"))
	if err != nil {
		return nil
	}
	var rows []store.PrincipalRow
	if json.Unmarshal(raw, &rows) != nil {
		return nil
	}
	return rows
}
