package grid

import "sort"

// YEntry is one sparse Y-bus complex entry.
type YEntry struct {
	Row string
	Col string
	G   float64
	B   float64
}

// BuildYBus assembles the complex bus admittance matrix including shunts.
func BuildYBus(buses []Bus, branches []Branch) map[[2]string]complex128 {
	y := make(map[[2]string]complex128)
	add := func(i, j string, v complex128) {
		key := [2]string{i, j}
		y[key] += v
	}
	for _, b := range buses {
		if b.GShunt != 0 || b.BShunt != 0 {
			add(b.ID, b.ID, complex(b.GShunt, b.BShunt))
		}
	}
	for _, br := range branches {
		if br.Status != "IN" {
			continue
		}
		add(br.From, br.From, br.Yff)
		add(br.From, br.To, br.Yft)
		add(br.To, br.From, br.Ytf)
		add(br.To, br.To, br.Ytt)
	}
	return y
}

// SortedYEntries returns nonzero Y-bus rows sorted by (row,col).
func SortedYEntries(y map[[2]string]complex128) []YEntry {
	keys := make([][2]string, 0, len(y))
	for k, v := range y {
		if v == 0 {
			continue
		}
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i][0] != keys[j][0] {
			return keys[i][0] < keys[j][0]
		}
		return keys[i][1] < keys[j][1]
	})
	out := make([]YEntry, 0, len(keys))
	for _, k := range keys {
		v := y[k]
		out = append(out, YEntry{Row: k[0], Col: k[1], G: real(v), B: imag(v)})
	}
	return out
}

// GB extracts conductance/susceptance matrices as maps.
func GB(y map[[2]string]complex128) (map[[2]string]float64, map[[2]string]float64) {
	g := make(map[[2]string]float64, len(y))
	b := make(map[[2]string]float64, len(y))
	for k, v := range y {
		g[k] = real(v)
		b[k] = imag(v)
	}
	return g, b
}
