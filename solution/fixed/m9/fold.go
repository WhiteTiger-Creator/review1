package m9

import (
	"hxenv/k4"
	"hxenv/lib/core"
)

func Fold(a, b, pin []byte) (core.State, error) {
	x, e := k4.Tile(a)
	if e != nil {
		return core.State{}, e
	}
	y, e := k4.Tile(b)
	if e != nil {
		return core.State{}, e
	}
	pins := k4.Sum(pin)

	type opt struct {
		e      core.Entry
		gen    int
		fromG1 bool
	}
	slot := map[string]opt{}
	present := map[string]map[string]core.Entry{}

	apply := func(t core.Tile, fromG1 bool) {
		for _, ent := range t.Entries {
			k := core.Key(ent.ModulePath, ent.Version)
			if present[k] == nil {
				present[k] = map[string]core.Entry{}
			}
			present[k][ent.Sum] = ent
			cur, ok := slot[k]
			if !ok {
				slot[k] = opt{e: ent, gen: t.Gen, fromG1: fromG1}
				continue
			}
			if t.Gen < cur.gen {
				slot[k] = opt{e: ent, gen: t.Gen, fromG1: fromG1}
			} else if t.Gen == cur.gen && fromG1 && !cur.fromG1 {
				slot[k] = opt{e: ent, gen: t.Gen, fromG1: true}
			}
		}
	}
	apply(x, true)
	apply(y, false)

	rows := map[string]core.Source{}
	for k, s := range slot {
		ent := s.e
		prov := map[string]bool{}
		for sum := range present[k] {
			prov[sum] = true
		}
		if pinSum, ok := pins[k]; ok {
			if alt, ok2 := present[k][pinSum]; ok2 {
				ent = alt
			}
		}
		rows[k] = core.Source{Entry: ent, Provenance: prov}
	}
	return core.State{Rows: rows, Needs: map[string]core.Need{}, Changes: map[string]core.Change{}}, nil
}
