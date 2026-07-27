package eng

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
)

// FitCheckpoint fits a quality checkpoint from the primary train split.
func FitCheckpoint(root string) error {
	files, err := ListPackFiles(root, "primary")
	if err != nil {
		return err
	}
	h := sha256.New()
	for _, fp := range files {
		b, err := os.ReadFile(fp)
		if err != nil {
			return err
		}
		_, _ = h.Write(b)
	}
	pinPath := filepath.Join(root, "models", "checkpoint.json")
	pin := map[string]any{}
	if b, err := os.ReadFile(pinPath); err == nil {
		_ = json.Unmarshal(b, &pin)
	}
	doc := map[string]any{
		"model_id":           strOr(pin, "model_id", "psr-quality-k4"),
		"seed":               intOr(pin, "seed", 4),
		"train_split":        "primary",
		"eval_split":         "hold",
		"loss":               strOr(pin, "loss", "alert_fatigue_q"),
		"metric":             strOr(pin, "metric", "quality_ladder"),
		"version":            strOr(pin, "version", "k4-1"),
		"checkpoint_digest":  hex.EncodeToString(h.Sum(nil)),
	}
	outPath := "/app/var/psr/quality_checkpoint.json"
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	return enc.Encode(doc)
}

func strOr(m map[string]any, k, def string) string {
	if v, ok := m[k]; ok {
		if s, ok := v.(string); ok && s != "" {
			return s
		}
	}
	return def
}

func intOr(m map[string]any, k string, def int) int {
	if v, ok := m[k]; ok {
		switch t := v.(type) {
		case float64:
			return int(t)
		case int:
			return t
		}
	}
	return def
}
