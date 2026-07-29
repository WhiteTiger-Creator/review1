package store

import (
	"encoding/json"
	"os"
)

type SegmentLedger struct {
	Epoch int
	Rows  []SegmentRow
}

func NewSegmentLedger() *SegmentLedger {
	return &SegmentLedger{Epoch: 0, Rows: nil}
}

func (l *SegmentLedger) Append(row SegmentRow) {
	l.Rows = append(l.Rows, row)
	if row.Epoch > l.Epoch {
		l.Epoch = row.Epoch
	}
}

func ReadJSON(path string, out any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, out)
}

func WriteJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}
