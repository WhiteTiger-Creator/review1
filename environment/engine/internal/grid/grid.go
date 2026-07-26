package grid

import (
	"fmt"
	"sort"
)

type Sector struct {
	ID   string `json:"id"`
	X    int    `json:"x"`
	Y    int    `json:"y"`
	Role string `json:"role,omitempty"`
}

type Graph struct {
	Sectors map[string]*Sector
	Edges   map[string]map[string]bool
}

func New() *Graph {
	return &Graph{
		Sectors: map[string]*Sector{},
		Edges:   map[string]map[string]bool{},
	}
}

func (g *Graph) AddSector(id string, x, y int, role string) error {
	if id == "" {
		return fmt.Errorf("empty sector id")
	}
	if _, ok := g.Sectors[id]; ok {
		return fmt.Errorf("duplicate sector %s", id)
	}
	for _, s := range g.Sectors {
		if s.X == x && s.Y == y {
			return fmt.Errorf("overlapping coordinates %d,%d", x, y)
		}
	}
	g.Sectors[id] = &Sector{ID: id, X: x, Y: y, Role: role}
	g.Edges[id] = map[string]bool{}
	return nil
}

func (g *Graph) AddEdge(a, b string) error {
	if g.Sectors[a] == nil || g.Sectors[b] == nil {
		return fmt.Errorf("invalid edge %s-%s", a, b)
	}
	if a == b {
		return fmt.Errorf("self-edge %s", a)
	}
	g.Edges[a][b] = true
	g.Edges[b][a] = true
	return nil
}

func (g *Graph) Neighbors(id string) []string {
	out := make([]string, 0, len(g.Edges[id]))
	for n := range g.Edges[id] {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}

func (g *Graph) HasEdge(a, b string) bool {
	return g.Edges[a] != nil && g.Edges[a][b]
}

func (g *Graph) Distance(a, b string) int {
	if a == b {
		return 0
	}
	type node struct {
		id string
		d  int
	}
	q := []node{{a, 0}}
	seen := map[string]bool{a: true}
	for len(q) > 0 {
		cur := q[0]
		q = q[1:]
		for _, n := range g.Neighbors(cur.id) {
			if n == b {
				return cur.d + 1
			}
			if !seen[n] {
				seen[n] = true
				q = append(q, node{n, cur.d + 1})
			}
		}
	}
	return -1
}

func (g *Graph) IDs() []string {
	ids := make([]string, 0, len(g.Sectors))
	for id := range g.Sectors {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func (g *Graph) Rotate90() *Graph {
	ng := New()
	for _, id := range g.IDs() {
		s := g.Sectors[id]
		// (x,y) -> (y, -x)
		_ = ng.AddSector(id, s.Y, -s.X, s.Role)
	}
	seen := map[string]bool{}
	for _, a := range g.IDs() {
		for _, b := range g.Neighbors(a) {
			key := a + "|" + b
			rkey := b + "|" + a
			if seen[key] || seen[rkey] {
				continue
			}
			seen[key] = true
			_ = ng.AddEdge(a, b)
		}
	}
	return ng
}

func (g *Graph) Rename(mapping map[string]string) (*Graph, error) {
	ng := New()
	for _, id := range g.IDs() {
		s := g.Sectors[id]
		nid, ok := mapping[id]
		if !ok {
			return nil, fmt.Errorf("missing rename for %s", id)
		}
		if err := ng.AddSector(nid, s.X, s.Y, s.Role); err != nil {
			return nil, err
		}
	}
	seen := map[string]bool{}
	for _, a := range g.IDs() {
		for _, b := range g.Neighbors(a) {
			key := a + "|" + b
			rkey := b + "|" + a
			if seen[key] || seen[rkey] {
				continue
			}
			seen[key] = true
			if err := ng.AddEdge(mapping[a], mapping[b]); err != nil {
				return nil, err
			}
		}
	}
	return ng, nil
}

func ValidateLane(g *Graph, lane []string) error {
	if len(lane) < 2 {
		return fmt.Errorf("lane too short")
	}
	for i := 0; i+1 < len(lane); i++ {
		if !g.HasEdge(lane[i], lane[i+1]) {
			return fmt.Errorf("impossible lane hop %s->%s", lane[i], lane[i+1])
		}
	}
	return nil
}
