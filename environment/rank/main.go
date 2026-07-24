package main

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type Impression struct {
	QueryID    int
	SerpRank   int
	DocID      int
	Clicked    int
	SessionDay int
	TemplateID string
	Features   []float64
}

func dataDir() string {
	if d := os.Getenv("DATA_DIR"); d != "" {
		return d
	}
	return "/app/data"
}

func outPath() string {
	if o := os.Getenv("OUT"); o != "" {
		return o
	}
	return "/app/output/ranker.json"
}

func main() {
	dir := dataDir()
	feats, nf := readFeatures(dir)
	queries := readQueries(dir)
	numSlots := readPageSlots(dir)

	raw := readImpressions(dir)
	imprs := make([]Impression, 0, len(raw))
	for _, im := range raw {
		v, ok := feats[[2]int{im.QueryID, im.DocID}]
		if !ok {
			continue
		}
		qr := queries[im.QueryID]
		im.Features = v
		im.SessionDay = qr.Day
		im.TemplateID = qr.Template
		imprs = append(imprs, im)
	}

	theta, w := Estimate(imprs, nf, numSlots, dir)

	out := map[string]interface{}{
		"slot_propensities": theta,
		"relevance_weights": w,
	}
	op := outPath()
	os.MkdirAll(filepath.Dir(op), 0o755)
	f, err := os.Create(op)
	if err != nil {
		os.Exit(1)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	if err := enc.Encode(out); err != nil {
		os.Exit(1)
	}
}
