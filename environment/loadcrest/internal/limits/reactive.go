package limits

import (
	"loadcrest/internal/deck"
	"loadcrest/internal/grid"
)

// Kind is UPPER or LOWER.
type Kind string

const (
	Upper Kind = "UPPER"
	Lower Kind = "LOWER"
)

// Candidate is a reactive-limit crossing detection.
type Candidate struct {
	BusID string
	Kind  Kind
	QLim  float64
	QGen  float64
}

// Detect returns no events in the starter boundary.
func Detect(buses []grid.Bus, y map[[2]string]complex128, demands map[string]deck.Demand, lambda, tol float64) []Candidate {
	_ = buses
	_ = y
	_ = demands
	_ = lambda
	_ = tol
	return nil
}

// ApplySwitch is a no-op in the starter boundary.
func ApplySwitch(buses []grid.Bus, busID string, kind Kind) {
	_ = buses
	_ = busID
	_ = kind
}
