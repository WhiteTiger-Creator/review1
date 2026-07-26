package p6

import (
	"hxenv/lib/core"
	"os"
	"path/filepath"
	"strings"
)

func Lay(p core.Plan, n string) error {
	have := map[string]bool{}
	hasLegacy := false
	var reqs []string
	var sums []string
	for _, e := range core.SortEdges(p.Edges) {
		have[e.ModulePath] = true
		if e.ModulePath == "example.com/lib/legacy" && e.ReplaceTo != "" {
			hasLegacy = true
			sums = append(sums, e.ModulePath+" "+e.Version+" "+e.Sum)
			continue
		}
		reqs = append(reqs, "\t"+e.ModulePath+" "+e.Version)
		if e.Sum != "" {
			sums = append(sums, e.ModulePath+" "+e.Version+" "+e.Sum)
		}
	}
	if hasLegacy || have["example.com/lib/legacy"] {
		reqs = append(reqs, "\texample.com/lib/legacy/v2 v2.0.0")
		hasLegacy = true
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
	if have["example.com/lib/a7x"] {
		b.WriteString("replace example.com/lib/a7x => ./mods/a7x\n")
	}
	if have["example.com/lib/b2x"] {
		b.WriteString("replace example.com/lib/b2x => ./mods/b2x\n")
	}
	if hasLegacy {
		b.WriteString("replace example.com/lib/legacy/v2 => ./mods/legacy_v2\n")
		b.WriteString("replace example.com/lib/legacy => example.com/lib/legacy/v2 v2.0.0\n")
	}
	modPath := filepath.Join(n, "go.mod")
	if e := os.WriteFile(modPath, []byte(b.String()), 0644); e != nil {
		return e
	}
	sumBody := strings.Join(sums, "\n")
	if sumBody != "" {
		sumBody += "\n"
	}
	return os.WriteFile(filepath.Join(n, "go.sum"), []byte(sumBody), 0644)
}

func Seal(n string) (string, error) {
	mod, e := os.ReadFile(filepath.Join(n, "go.mod"))
	if e != nil {
		return "", e
	}
	sum, e := os.ReadFile(filepath.Join(n, "go.sum"))
	if e != nil {
		sum = nil
	}
	return core.FingerHex(mod, sum), nil
}
