package p6

import (
	"hxenv/lib/core"
	"os"
	"path/filepath"
	"strings"
)

func Lay(p core.Plan, n string) error {
	modPath := filepath.Join(n, "go.mod")
	existing, _ := os.ReadFile(modPath)
	have := map[string]bool{}
	hasLegacy := false
	var reqs []string
	for _, e := range core.SortEdges(p.Edges) {
		have[e.ModulePath] = true
		reqs = append(reqs, "\t"+e.ModulePath+" "+e.Version)
		if e.ReplaceTo != "" && e.ModulePath == "example.com/lib/legacy" {
			hasLegacy = true
		}
	}
	for _, line := range strings.Split(string(existing), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "example.com/lib/") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				reqs = append(reqs, "\t"+fields[0]+" "+fields[1])
			}
		}
	}
	if hasLegacy || have["example.com/lib/legacy"] {
		reqs = append(reqs, "\texample.com/lib/legacy/v2 v2.0.0")
	}
	seen := map[string]bool{}
	var uniq []string
	for _, r := range reqs {
		if seen[r] {
			continue
		}
		seen[r] = true
		uniq = append(uniq, r)
	}
	var b strings.Builder
	b.WriteString("module example.com/nest\n\ngo 1.22\n\nrequire (\n")
	b.WriteString(strings.Join(uniq, "\n"))
	b.WriteString("\n)\n\n")
	b.WriteString("replace example.com/lib/root => ./mods/root\n")
	b.WriteString("replace example.com/lib/bind => ./mods/bind\n")
	b.WriteString("replace example.com/lib/a7x => ./mods/a7x\n")
	b.WriteString("replace example.com/lib/b2x => ./mods/b2x\n")
	b.WriteString("replace example.com/lib/legacy/v2 => ./mods/legacy_v2\n")
	if hasLegacy {
		b.WriteString("replace example.com/lib/legacy => example.com/lib/legacy/v2 v2.0.0\n")
	}
	if e := os.WriteFile(modPath, []byte(b.String()), 0644); e != nil {
		return e
	}
	return os.WriteFile(filepath.Join(n, "go.sum"), []byte{}, 0644)
}

func Seal(n string) (string, error) {
	b, e := os.ReadFile(filepath.Join(n, "go.mod"))
	if e != nil {
		return "", e
	}
	return core.FingerHex(b), nil
}
