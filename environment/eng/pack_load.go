package eng

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

// Pack is one campaign corpus file.
type Pack struct {
	ID    string    `json:"id"`
	Mode  int       `json:"mode"`
	Gen   int       `json:"gen"`
	Prior []float64 `json:"prior"`
	Cuts  []float64 `json:"cuts"`
	Ch    []struct {
		Sid string    `json:"sid"`
		SL  float64   `json:"sl"`
		Tr  []float64 `json:"tr"`
	} `json:"ch"`
}

// LoadPack reads a corpus JSON file.
func LoadPack(path string) (Pack, error) {
	var p Pack
	b, err := os.ReadFile(path)
	if err != nil {
		return p, err
	}
	err = json.Unmarshal(b, &p)
	return p, err
}

// ListPackFiles returns sorted corpus paths under root/corp/sub.
func ListPackFiles(root, sub string) ([]string, error) {
	dir := filepath.Join(root, "corp", sub)
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for _, e := range ents {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if len(name) < 5 || name[len(name)-5:] != ".json" {
			continue
		}
		out = append(out, filepath.Join(dir, name))
	}
	sort.Strings(out)
	return out, nil
}
