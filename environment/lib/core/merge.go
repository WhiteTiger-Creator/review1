package core

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
)

func Classify(path, replaceTo string) string {
	if replaceTo != "" {
		return "prop"
	}
	switch path {
	case "example.com/lib/root":
		return "root"
	case "example.com/lib/bind":
		return "bind"
	case "example.com/lib/b2x":
		return "sys"
	case "example.com/lib/a7x":
		return "other"
	default:
		return "other"
	}
}

func HasArm(arms map[string]bool, path string) bool {
	switch path {
	case "example.com/lib/root", "example.com/lib/bind", "example.com/lib/legacy", "example.com/lib/legacy/v2":
		return arms["a7"] || arms["b2"]
	case "example.com/lib/a7x":
		return arms["a7"]
	case "example.com/lib/b2x":
		return arms["b2"]
	default:
		return arms["a7"] || arms["b2"]
	}
}

func Key(path, ver string) string {
	return path + "@" + ver
}

func SortEdges(edges []Edge) []Edge {
	out := append([]Edge{}, edges...)
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].ModulePath == out[j].ModulePath {
			return out[i].Version < out[j].Version
		}
		return out[i].ModulePath < out[j].ModulePath
	})
	return out
}

func ViewDigest(edges []Edge) (string, error) {
	sorted := SortEdges(edges)
	rows := make([]map[string]any, 0, len(sorted))
	for _, e := range sorted {
		rows = append(rows, map[string]any{
			"cls":         e.Cls,
			"module_path": e.ModulePath,
			"replace_to":  e.ReplaceTo,
			"sum":         e.Sum,
			"version":     e.Version,
		})
	}
	payload, err := json.Marshal(rows)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func FingerHex(parts ...[]byte) string {
	h := sha256.New()
	for _, p := range parts {
		h.Write(p)
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil))
}
