package equations

import (
	"math"

	"loadcrest/internal/deck"
	"loadcrest/internal/grid"
)

// SpecPQ returns specified net injections at lambda.
func SpecPQ(buses []grid.Bus, demands map[string]deck.Demand, lambda float64) (sp, sq map[string]float64) {
	sp = make(map[string]float64, len(buses))
	sq = make(map[string]float64, len(buses))
	for _, b := range buses {
		dp, dq := 0.0, 0.0
		if d, ok := demands[b.ID]; ok {
			dp, dq = d.DeltaP, d.DeltaQ
		}
		pload := b.PLoad0 + lambda*dp
		qload := b.QLoad0 + lambda*dq
		sp[b.ID] = b.PGen - pload
		if b.Type == deck.BusPQ {
			sq[b.ID] = b.QGen - qload
		} else {
			sq[b.ID] = 0 // unused for PV/slack mismatch
		}
	}
	return sp, sq
}

// Mismatch builds F(x,lambda) under POWER-07.
func Mismatch(buses []grid.Bus, lay Layout, y map[[2]string]complex128, demands map[string]deck.Demand, lambda float64) []float64 {
	p, q := Injections(buses, y)
	sp, sq := SpecPQ(buses, demands, lambda)
	f := make([]float64, lay.Dim())
	for i, id := range lay.AngleBusIDs {
		f[i] = sp[id] - p[id]
	}
	off := len(lay.AngleBusIDs)
	for i, id := range lay.PQMagBusIDs {
		f[off+i] = sq[id] - q[id]
	}
	return f
}

// MaxAbs returns max |f_i|.
func MaxAbs(f []float64) float64 {
	m := 0.0
	for _, v := range f {
		a := math.Abs(v)
		if a > m {
			m = a
		}
	}
	return m
}

// FLambda is ∂F/∂λ from load directions.
func FLambda(buses []grid.Bus, lay Layout, demands map[string]deck.Demand) []float64 {
	fl := make([]float64, lay.Dim())
	for i, id := range lay.AngleBusIDs {
		if d, ok := demands[id]; ok {
			fl[i] = -d.DeltaP
		}
	}
	off := len(lay.AngleBusIDs)
	for i, id := range lay.PQMagBusIDs {
		if d, ok := demands[id]; ok {
			fl[off+i] = -d.DeltaQ
		}
	}
	return fl
}

// PVQGen returns Q_gen = Q_inj + Q_load for an unswitched PV bus.
func PVQGen(bus grid.Bus, qInj float64, demands map[string]deck.Demand, lambda float64) float64 {
	dq := 0.0
	if d, ok := demands[bus.ID]; ok {
		dq = d.DeltaQ
	}
	return qInj + bus.QLoad0 + lambda*dq
}
