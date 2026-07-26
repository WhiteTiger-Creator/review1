package m9

import (
	"hxenv/k4"
	"hxenv/lib/core"
	"strings"
)

func Close(s core.State, scraps [][]byte, sum []byte, arms string) (core.Plan, error) {
	s.Needs, s.Changes = k4.Scraps(scraps)
	sums := map[string]string{}
	for k, src := range s.Rows {
		sums[k] = src.Entry.Sum
	}
	for k, v := range k4.Sum(sum) {
		sums[k] = v
	}
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
		rt := ""
		lookupPath, lookupVer := n.ModulePath, n.Version
		if c, ok := s.Changes[n.ModulePath]; ok && c.To != "" {
			rt = c.To + " " + c.ToVersion
			lookupPath, lookupVer = c.To, c.ToVersion
		}
		sumv := sums[core.Key(lookupPath, lookupVer)]
		if sumv == "" {
			sumv = sums[core.Key(n.ModulePath, n.Version)]
		}
		if sumv == "" {
			continue
		}
		out.Edges = append(out.Edges, core.Edge{
			ModulePath: n.ModulePath,
			Version:    n.Version,
			ReplaceTo:  rt,
			Cls:        core.Classify(lookupPath, ""),
			Sum:        sumv,
		})
	}
	out.Edges = core.SortEdges(out.Edges)
	return out, nil
}
