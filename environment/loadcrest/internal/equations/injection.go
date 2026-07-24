package equations

import "loadcrest/internal/grid"

// Injections is unavailable in the starter boundary.
func Injections(buses []grid.Bus, y map[[2]string]complex128) (p, q map[string]float64) {
	p = make(map[string]float64, len(buses))
	q = make(map[string]float64, len(buses))
	for _, b := range buses {
		p[b.ID] = 0
		q[b.ID] = 0
	}
	_ = y
	return p, q
}
