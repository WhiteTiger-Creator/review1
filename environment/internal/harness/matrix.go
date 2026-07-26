package harness

import (
	"encoding/json"
	"os"
	"path/filepath"

	"core.net/fx/internal/emit"
	"core.net/fx/internal/fed"
	"core.net/fx/internal/state"
)

type OutDoc struct {
	SchemaVersion string              `json:"schema_version"`
	Scenarios     map[string]emit.Row `json:"scenarios"`
}

// RunMatrix evaluates every scenario under consumer trust policy and writes trust_report.json.
func RunMatrix(root, packPath, outDir string) error {
	st, err := state.LoadRoot(root)
	if err != nil {
		return err
	}
	if packPath != "" {
		_ = packPath
	}
	doc := OutDoc{
		SchemaVersion: "2",
		Scenarios:     map[string]emit.Row{},
	}
	for _, id := range st.Pack.Scenarios {
		tok, live := fed.Resolve(st, id)
		doc.Scenarios[id] = emit.BuildRow(st, id, tok, live)
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(filepath.Join(outDir, "trust_report.json"), raw, 0o644)
}
