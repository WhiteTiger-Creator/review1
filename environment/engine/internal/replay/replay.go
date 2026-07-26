package replay

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type Generation struct {
	Summary         map[string]any   `json:"summary"`
	Rounds          []map[string]any `json:"rounds"`
	Contacts        map[string]any   `json:"contacts"`
	Signals         []map[string]any `json:"signals"`
	Power           map[string]any   `json:"power"`
	Civilians       map[string]any   `json:"civilians"`
	BotDiagnostics  map[string]any   `json:"bot_diagnostics"`
}

func StageAndPublish(outputRoot string, gen Generation, inject string) (string, error) {
	if err := os.MkdirAll(outputRoot, 0o755); err != nil {
		return "", err
	}
	genRoot := filepath.Join(outputRoot, "generations")
	if err := os.MkdirAll(genRoot, 0o755); err != nil {
		return "", err
	}
	name := generationName(gen)
	staging := filepath.Join(outputRoot, ".staging-"+name)
	_ = os.RemoveAll(staging)
	if err := os.MkdirAll(staging, 0o755); err != nil {
		return "", err
	}
	defer func() { _ = os.RemoveAll(staging) }()

	if inject == "write" {
		return "", fmt.Errorf("injected write failure")
	}

	files := map[string]any{
		"summary.json":         gen.Summary,
		"contacts.json":        gen.Contacts,
		"power.json":           gen.Power,
		"civilians.json":       gen.Civilians,
		"bot-diagnostics.json": gen.BotDiagnostics,
	}
	for fn, v := range files {
		if err := writeJSON(filepath.Join(staging, fn), v); err != nil {
			return "", err
		}
	}
	if err := writeJSONL(filepath.Join(staging, "rounds.jsonl"), gen.Rounds); err != nil {
		return "", err
	}
	if err := writeJSONL(filepath.Join(staging, "signals.jsonl"), gen.Signals); err != nil {
		return "", err
	}

	if err := validateGeneration(gen); err != nil {
		return "", err
	}
	if inject == "validate" {
		return "", fmt.Errorf("injected validate failure")
	}

	// Flush directory entries
	if d, err := os.Open(staging); err == nil {
		_ = d.Sync()
		_ = d.Close()
	}

	finalDir := filepath.Join(genRoot, name)
	if inject == "rename" {
		return "", fmt.Errorf("injected rename failure")
	}
	_ = os.RemoveAll(finalDir)
	if err := os.Rename(staging, finalDir); err != nil {
		return "", err
	}
	// staging moved; prevent defer remove of final
	staging = ""

	current := filepath.Join(outputRoot, "current")
	tmpLink := filepath.Join(outputRoot, ".current-tmp")
	rel := filepath.Join("generations", name)
	_ = os.Remove(tmpLink)
	if err := os.WriteFile(tmpLink, []byte(rel+"\n"), 0o644); err != nil {
		return "", err
	}
	if inject == "pointer" {
		_ = os.Remove(tmpLink)
		return "", fmt.Errorf("injected pointer failure")
	}
	if err := os.Rename(tmpLink, current); err != nil {
		return "", err
	}
	return finalDir, nil
}

func generationName(gen Generation) string {
	scenario, _ := gen.Summary["scenario"].(string)
	seed := fmt.Sprintf("%v", gen.Summary["seed"])
	doctrine, _ := gen.Summary["partner_doctrine"].(string)
	score := fmt.Sprintf("%v", gen.Summary["score"])
	return fmt.Sprintf("%s_s%s_%s_sc%s", sanitize(scenario), seed, sanitize(doctrine), score)
}

func sanitize(s string) string {
	out := make([]rune, 0, len(s))
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '-' || r == '_' {
			out = append(out, r)
		} else {
			out = append(out, '_')
		}
	}
	if len(out) == 0 {
		return "gen"
	}
	return string(out)
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	f, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	if _, err := f.Write(b); err != nil {
		_ = f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		_ = f.Close()
		return err
	}
	return f.Close()
}

func writeJSONL(path string, rows []map[string]any) error {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	enc := json.NewEncoder(f)
	for _, row := range rows {
		keys := make([]string, 0, len(row))
		for k := range row {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		ordered := map[string]any{}
		for _, k := range keys {
			ordered[k] = row[k]
		}
		if err := enc.Encode(ordered); err != nil {
			_ = f.Close()
			return err
		}
	}
	if err := f.Sync(); err != nil {
		_ = f.Close()
		return err
	}
	return f.Close()
}

func validateGeneration(gen Generation) error {
	if gen.Summary == nil {
		return fmt.Errorf("missing summary")
	}
	if _, ok := gen.Summary["score"]; !ok {
		return fmt.Errorf("summary missing score")
	}
	if gen.Contacts == nil {
		return fmt.Errorf("missing contacts")
	}
	if gen.Power == nil {
		return fmt.Errorf("missing power")
	}
	if gen.Civilians == nil {
		return fmt.Errorf("missing civilians")
	}
	score, _ := asInt(gen.Summary["score"])
	recon, _ := asInt(gen.Summary["score_reconciled"])
	if recon != 0 && score != recon {
		return fmt.Errorf("score reconciliation failed")
	}
	return nil
}

func asInt(v any) (int, bool) {
	switch t := v.(type) {
	case int:
		return t, true
	case int64:
		return int(t), true
	case float64:
		return int(t), true
	default:
		return 0, false
	}
}

func ReadCurrent(outputRoot string) (string, error) {
	b, err := os.ReadFile(filepath.Join(outputRoot, "current"))
	if err != nil {
		return "", err
	}
	rel := string(b)
	for len(rel) > 0 && (rel[len(rel)-1] == '\n' || rel[len(rel)-1] == '\r') {
		rel = rel[:len(rel)-1]
	}
	return filepath.Join(outputRoot, rel), nil
}
