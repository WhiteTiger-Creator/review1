package eng

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// JRec is one per-sid campaign journal record under var/journal.
type JRec struct {
	Gen    int       `json:"gen"`
	Bands  []float64 `json:"bands"`
	Cls    []int     `json:"cls"`
	Q      []float64 `json:"q"`
	EvalFP string    `json:"eval_fp"`
}

func journalDir(root string) string {
	return filepath.Join(root, "var", "journal")
}

// LoadJournal reads a sid record when present.
func LoadJournal(root, sid string) (JRec, bool) {
	path := filepath.Join(journalDir(root), sid+".json")
	b, err := os.ReadFile(path)
	if err != nil {
		return JRec{}, false
	}
	var rec JRec
	if err := json.Unmarshal(b, &rec); err != nil {
		return JRec{}, false
	}
	return rec, true
}

// SaveJournal writes a sid record, replacing any prior body.
func SaveJournal(root, sid string, rec JRec) error {
	dir := journalDir(root)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(dir, sid+".json")
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	return enc.Encode(rec)
}

// SeedCache copies journal bands into an epoch cache when gen matches.
func SeedCache(cache map[int]float64, rec JRec, wantGen int) {
	if rec.Gen != wantGen {
		return
	}
	for i, v := range rec.Bands {
		cache[i] = v
	}
}
