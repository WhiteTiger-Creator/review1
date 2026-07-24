package equations

import (
	"sort"

	"loadcrest/internal/deck"
	"loadcrest/internal/grid"
)

// Layout describes POWER-06 ordering; starter omits live bus-type switching behavior.
type Layout struct {
	AngleBusIDs []string
	PQMagBusIDs []string
	BusIndex    map[string]int
}

// BuildLayout returns a fixed declared-type layout without PV→PQ expansion.
func BuildLayout(buses []grid.Bus) Layout {
	idx := map[string]int{}
	var angles, mags []string
	for i, b := range buses {
		idx[b.ID] = i
		if b.DeclaredType == deck.BusSlack {
			continue
		}
		angles = append(angles, b.ID)
		if b.DeclaredType == deck.BusPQ {
			mags = append(mags, b.ID)
		}
	}
	sort.Strings(angles)
	sort.Strings(mags)
	return Layout{AngleBusIDs: angles, PQMagBusIDs: mags, BusIndex: idx}
}

func (l Layout) Dim() int { return len(l.AngleBusIDs) + len(l.PQMagBusIDs) }

func PackState(buses []grid.Bus, lay Layout) []float64 {
	x := make([]float64, lay.Dim())
	for i, id := range lay.AngleBusIDs {
		x[i] = buses[lay.BusIndex[id]].AngleRad
	}
	off := len(lay.AngleBusIDs)
	for i, id := range lay.PQMagBusIDs {
		x[off+i] = buses[lay.BusIndex[id]].V
	}
	return x
}

func UnpackState(buses []grid.Bus, lay Layout, x []float64) {
	for i, id := range lay.AngleBusIDs {
		buses[lay.BusIndex[id]].AngleRad = x[i]
	}
	off := len(lay.AngleBusIDs)
	for i, id := range lay.PQMagBusIDs {
		buses[lay.BusIndex[id]].V = x[off+i]
	}
}

func ZPack(x []float64, lambda float64) []float64 {
	z := make([]float64, len(x)+1)
	copy(z, x)
	z[len(x)] = lambda
	return z
}

func ZUnpack(z []float64) (x []float64, lambda float64) {
	n := len(z) - 1
	x = make([]float64, n)
	copy(x, z[:n])
	return x, z[n]
}
