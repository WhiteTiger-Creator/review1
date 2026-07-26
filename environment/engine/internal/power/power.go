package power

import (
	"fmt"
	"sort"
)

type Generator struct {
	ID       string   `json:"id"`
	Sector   string   `json:"sector"`
	Capacity int      `json:"capacity"`
	Links    []string `json:"links"`
	Load     int      `json:"load"`
	Overload bool     `json:"overload"`
	Damaged  bool     `json:"damaged"`
}

type Battery struct {
	Owner   string `json:"owner"`
	Charge  int    `json:"charge"`
	Max     int    `json:"max"`
	Cooldown int   `json:"cooldown"`
}

type System struct {
	Generators map[string]*Generator
	Batteries  map[string]*Battery
	ScanLoad   map[string]int
	ShieldChg  map[string]int
}

func New() *System {
	return &System{
		Generators: map[string]*Generator{},
		Batteries:  map[string]*Battery{},
		ScanLoad:   map[string]int{},
		ShieldChg:  map[string]int{},
	}
}

func (s *System) AddGenerator(g Generator) error {
	if g.ID == "" || g.Capacity < 0 {
		return fmt.Errorf("invalid generator")
	}
	if len(g.Links) == 0 {
		return fmt.Errorf("generator %s missing links", g.ID)
	}
	cp := g
	cp.Links = append([]string(nil), g.Links...)
	sort.Strings(cp.Links)
	s.Generators[g.ID] = &cp
	return nil
}

func (s *System) AddBattery(owner string, charge, max int) {
	s.Batteries[owner] = &Battery{Owner: owner, Charge: charge, Max: max}
}

func (s *System) LinkedGenerators(owner string) []*Generator {
	out := []*Generator{}
	for _, id := range s.GeneratorIDs() {
		g := s.Generators[id]
		for _, link := range g.Links {
			if link == owner {
				out = append(out, g)
				break
			}
		}
	}
	return out
}

func (s *System) Available(owner string) int {
	total := 0
	if bat := s.Batteries[owner]; bat != nil {
		total += bat.Charge
	}
	for _, g := range s.LinkedGenerators(owner) {
		if g.Damaged || g.Overload {
			continue
		}
		remain := g.Capacity - g.Load
		if remain > 0 {
			total += remain
		}
	}
	return total
}

func (s *System) Spend(owner string, cost int) error {
	if cost <= 0 {
		return nil
	}
	if s.Available(owner) < cost {
		return fmt.Errorf("insufficient power for %s", owner)
	}
	remain := cost
	// Prefer generators first (shared), then battery — but for reservation fairness:
	// spend local battery last; shared generators first in id order.
	for _, g := range s.LinkedGenerators(owner) {
		if remain == 0 {
			break
		}
		if g.Damaged || g.Overload {
			continue
		}
		space := g.Capacity - g.Load
		if space <= 0 {
			continue
		}
		use := space
		if use > remain {
			use = remain
		}
		g.Load += use
		remain -= use
		if g.Load > g.Capacity {
			g.Overload = true
		}
	}
	if remain > 0 {
		bat := s.Batteries[owner]
		if bat == nil || bat.Charge < remain {
			return fmt.Errorf("power spend failed for %s", owner)
		}
		bat.Charge -= remain
	}
	return nil
}

func (s *System) TryOverload(owner string, cost int) error {
	// Spend even if it pushes overload when capacity is exact-boundary contested.
	if err := s.Spend(owner, cost); err != nil {
		return err
	}
	for _, g := range s.LinkedGenerators(owner) {
		if g.Load >= g.Capacity && cost >= 2 {
			// borderline: mark overload if load equals capacity after heavy draw contention
			if g.Load == g.Capacity {
				// leave as is
			}
		}
	}
	return nil
}

func (s *System) MarkOverloadIfExceeded() {
	for _, id := range s.GeneratorIDs() {
		g := s.Generators[id]
		if g.Load > g.Capacity {
			g.Overload = true
			g.Damaged = true
		}
	}
}

func (s *System) TickRound() {
	for _, id := range s.GeneratorIDs() {
		g := s.Generators[id]
		g.Load = 0
		if g.Overload {
			// stay damaged until repaired
			g.Overload = false
		}
	}
	for _, id := range s.BatteryOwners() {
		b := s.Batteries[id]
		if b.Cooldown > 0 {
			b.Cooldown--
		}
		if b.Charge < b.Max {
			b.Charge++
		}
	}
}

func (s *System) Repair(owner, genID string) error {
	g := s.Generators[genID]
	if g == nil {
		return fmt.Errorf("unknown generator")
	}
	linked := false
	for _, l := range g.Links {
		if l == owner {
			linked = true
			break
		}
	}
	if !linked {
		return fmt.Errorf("generator not linked")
	}
	if err := s.Spend(owner, 2); err != nil {
		return err
	}
	g.Damaged = false
	g.Overload = false
	g.Load = 0
	return nil
}

func (s *System) GeneratorIDs() []string {
	ids := make([]string, 0, len(s.Generators))
	for id := range s.Generators {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func (s *System) BatteryOwners() []string {
	ids := make([]string, 0, len(s.Batteries))
	for id := range s.Batteries {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func (s *System) Snapshot() map[string]any {
	gens := []map[string]any{}
	for _, id := range s.GeneratorIDs() {
		g := s.Generators[id]
		gens = append(gens, map[string]any{
			"id": g.ID, "sector": g.Sector, "capacity": g.Capacity,
			"load": g.Load, "overload": g.Overload, "damaged": g.Damaged,
			"links": append([]string(nil), g.Links...),
		})
	}
	bats := []map[string]any{}
	for _, id := range s.BatteryOwners() {
		b := s.Batteries[id]
		bats = append(bats, map[string]any{
			"owner": b.Owner, "charge": b.Charge, "max": b.Max, "cooldown": b.Cooldown,
		})
	}
	return map[string]any{"generators": gens, "batteries": bats}
}
