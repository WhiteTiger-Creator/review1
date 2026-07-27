package util

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

func Sha16(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])[:16]
}

func FmtWeight(w float64, decimals int) string {
	return strconv.FormatFloat(w, 'f', decimals, 64)
}

type Item struct {
	ItemID string  `json:"item_id"`
	Prior  float64 `json:"prior"`
	Signal float64 `json:"signal"`
}

type Seed struct {
	ID    string `json:"id"`
	Items []Item `json:"items"`
}

func LoadSeeds(dir string) ([]Seed, error) {
	matches, err := filepath.Glob(filepath.Join(dir, "seed_*.json"))
	if err != nil {
		return nil, err
	}
	sort.Strings(matches)
	out := make([]Seed, 0, len(matches))
	for _, m := range matches {
		b, err := os.ReadFile(m)
		if err != nil {
			return nil, err
		}
		var s Seed
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no seeds in %s", dir)
	}
	return out, nil
}
