package vault

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
)

func NewLedger(dir string) *Ledger {
	return &Ledger{
		Path:    filepath.Join(dir, "wal.jsonl"),
		Entries: nil,
		SnapW:   map[string]float64{},
	}
}

func (l *Ledger) Persist() error {
	if l == nil {
		return errNilLedger
	}
	if err := os.MkdirAll(filepath.Dir(l.Path), 0o755); err != nil {
		return err
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	for _, e := range l.Entries {
		if err := enc.Encode(e); err != nil {
			return err
		}
	}
	if err := os.WriteFile(l.Path, buf.Bytes(), 0o644); err != nil {
		return err
	}
	meta := map[string]any{
		"barrier":    l.Barrier,
		"snap":       l.SnapW,
		"trust_snap": l.TrustSnap,
	}
	mb, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(l.Path+".meta.json", mb, 0o644)
}

func (l *Ledger) Load() error {
	if l == nil {
		return errNilLedger
	}
	b, err := os.ReadFile(l.Path)
	if err != nil {
		if os.IsNotExist(err) {
			l.Entries = nil
			return nil
		}
		return err
	}
	l.Entries = nil
	dec := json.NewDecoder(bytes.NewReader(b))
	for {
		var e Entry
		if err := dec.Decode(&e); err != nil {
			if err == io.EOF {
				break
			}
			return err
		}
		l.Entries = append(l.Entries, e)
	}
	mb, err := os.ReadFile(l.Path + ".meta.json")
	if err == nil {
		var meta struct {
			Barrier   int                `json:"barrier"`
			Snap      map[string]float64 `json:"snap"`
			TrustSnap bool               `json:"trust_snap"`
		}
		if json.Unmarshal(mb, &meta) == nil {
			l.Barrier = meta.Barrier
			l.SnapW = meta.Snap
			l.TrustSnap = meta.TrustSnap
		}
	}
	return nil
}
