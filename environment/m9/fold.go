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
	chosen := x
	if y.Gen >= x.Gen {
		chosen = y
	}
	rows := map[string]core.Source{}
	for _, r := range chosen.Entries {
		key := core.Key(r.ModulePath, r.Version)
		if v, ok := pins[key]; ok {
			r.Sum = v
		}
		rows[key] = core.Source{Entry: r, Provenance: map[string]bool{r.Sum: true}}
	}
	return core.State{Rows: rows, Needs: map[string]core.Need{}, Changes: map[string]core.Change{}}, nil
}
