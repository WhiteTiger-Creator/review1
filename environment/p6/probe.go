package p6

import (
	"encoding/json"
	"hxenv/lib/core"
	"os"
	"path/filepath"
)

func Probe(p core.Plan, out string) error {
	d, e := core.ViewDigest(p.Edges)
	if e != nil {
		return e
	}
	b, e := json.MarshalIndent(struct {
		Edges      []core.Edge `json:"edges"`
		EdgeCount  int         `json:"edge_count"`
		ViewDigest string      `json:"view_digest"`
	}{core.SortEdges(p.Edges), len(p.Edges), d}, "", "  ")
	if e != nil {
		return e
	}
	if e = os.MkdirAll(filepath.Dir(out), 0755); e != nil {
		return e
	}
	return os.WriteFile(out, b, 0644)
}
