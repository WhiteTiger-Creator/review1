package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"gwc/catalog"
	"gwc/drive"
	"gwc/scroll"
	"gwc/store"
)

func main() {
	root := flag.String("root", "/app/environment", "tree root")
	out := flag.String("out", "/app/output", "output dir")
	cycles := flag.Int("cycles", 2, "shift count")
	flag.Parse()

	if err := os.MkdirAll(*out, 0o755); err != nil {
		fatal(err)
	}
	stateDir := filepath.Join(*root, "state")
	if err := os.MkdirAll(stateDir, 0o755); err != nil {
		fatal(err)
	}

	if ShouldSettle(*out) {
		return
	}

	priorTraces := loadPriorTraces(*out)

	cat, err := catalog.Load(*root)
	if err != nil {
		fatal(err)
	}
	ctx := &store.Ctx{StateDir: stateDir, OutDir: *out}

	result := drive.RunExport(ctx, cat, *cycles)
	traces := result.Traces
	if len(priorTraces) > 0 {
		traces = append(priorTraces, traces...)
	}

	writeJSON(filepath.Join(*out, "binding_transcript.json"), result.Binds)
	writeJSON(filepath.Join(*out, "auth_trace.json"), traces)
	writeJSONL(filepath.Join(*out, "probe_report.jsonl"), result.Probes)
	writeJSONLJournal(filepath.Join(*out, "auth_journal.jsonl"), scroll.Snapshot())
	writeJSON(filepath.Join(*out, "converge_report.json"), store.ConvergeReport{Cycles: result.Scopes})
}

func writeJSON(path string, v any) {
	raw, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		fatal(err)
	}
}

func writeJSONL(path string, rows []store.ProbeRow) {
	f, err := os.Create(path)
	if err != nil {
		fatal(err)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	for _, r := range rows {
		if err := enc.Encode(r); err != nil {
			fatal(err)
		}
	}
}

func writeJSONLJournal(path string, rows []store.JournalRow) {
	f, err := os.Create(path)
	if err != nil {
		fatal(err)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	for _, r := range rows {
		if err := enc.Encode(r); err != nil {
			fatal(err)
		}
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
