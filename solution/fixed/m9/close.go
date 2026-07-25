package m9

import (
	"hxenv/k4"
	"hxenv/lib/core"
	"strings"
)

func Close(s core.State, scraps [][]byte, sum []byte, arms string) (core.Plan, error) {
	s.Needs, s.Changes = k4.Scraps(scraps)
	arm := map[string]bool{}
	for _, a := range strings.Split(arms, ",") {
		a = strings.TrimSpace(a)
		if a != "" {
			arm[a] = true
		}
	}
	out := core.Plan{}
	for _, n := range s.Needs {
		if !core.HasArm(arm, n.ModulePath) {
			continue
		}
		src, ok := s.Rows[core.Key(n.ModulePath, n.Version)]
		if !ok || src.Entry.Sum == "" {
			continue
		}
		e := src.Entry
		rt := ""
		if c, ok := s.Changes[e.ModulePath]; ok && c.To != "" {
			rt = c.To + " " + c.ToVersion
		}
		out.Edges = append(out.Edges, core.Edge{
			ModulePath: e.ModulePath,
			Version:    e.Version,
			ReplaceTo:  rt,
			Cls:        core.Classify(e.ModulePath, rt),
			Sum:        e.Sum,
		})
	}
	out.Edges = core.SortEdges(out.Edges)
	return out, nil
}
