package threats

import (
	"sort"
)

const (
	KindIncursion = "incursion"
	KindFalse     = "false"
)

type Spec struct {
	ID         string   `json:"id"`
	SpawnRound int      `json:"spawn_round"`
	Lane       []string `json:"lane"`
	Kind       string   `json:"kind"`
	Speed      int      `json:"speed"`
	HP         int      `json:"hp"`
	BranchAt   int      `json:"branch_at,omitempty"`
	BranchLane []string `json:"branch_lane,omitempty"`
}

type Active struct {
	ID         string
	Kind       string
	Lane       []string
	Index      int
	HP         int
	Speed      int
	Alive      bool
	CapturedBy string
	Escaped    bool
	Visible    bool
	Confirmed  bool
}

func Spawn(specs []Spec, round int) []*Active {
	out := []*Active{}
	for _, s := range specs {
		if s.SpawnRound != round {
			continue
		}
		speed := s.Speed
		if speed < 1 {
			speed = 1
		}
		hp := s.HP
		if hp < 1 {
			hp = 1
		}
		kind := s.Kind
		if kind == "" {
			kind = KindIncursion
		}
		out = append(out, &Active{
			ID:    s.ID,
			Kind:  kind,
			Lane:  append([]string(nil), s.Lane...),
			Index: 0,
			HP:    hp,
			Speed: speed,
			Alive: true,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}

func (t *Active) Sector() string {
	if t == nil || !t.Alive || t.Index < 0 || t.Index >= len(t.Lane) {
		return ""
	}
	return t.Lane[t.Index]
}

func Advance(active []*Active, branchSpecs map[string]Spec) {
	sort.SliceStable(active, func(i, j int) bool { return active[i].ID < active[j].ID })
	for _, t := range active {
		if !t.Alive || t.Escaped || t.CapturedBy != "" {
			continue
		}
		for step := 0; step < t.Speed; step++ {
			if spec, ok := branchSpecs[t.ID]; ok && spec.BranchAt == t.Index && len(spec.BranchLane) > 0 {
				// deterministic branch: take branch lane from current
				rest := append([]string{t.Sector()}, spec.BranchLane...)
				t.Lane = rest
				t.Index = 0
			}
			if t.Index+1 >= len(t.Lane) {
				if t.Kind == KindIncursion {
					t.Escaped = true
					t.Alive = false
				} else {
					t.Alive = false
				}
				break
			}
			t.Index++
		}
	}
}

func SortedIDs(active []*Active) []string {
	ids := make([]string, 0, len(active))
	for _, t := range active {
		ids = append(ids, t.ID)
	}
	sort.Strings(ids)
	return ids
}
