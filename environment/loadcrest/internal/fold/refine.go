package fold

import (
	"fmt"

	"loadcrest/internal/deck"
	"loadcrest/internal/equations"
	"loadcrest/internal/grid"
)

// CorrectFn performs one augmented corrector.
type CorrectFn func(buses []grid.Bus, lay equations.Layout, y map[[2]string]complex128, demands map[string]deck.Demand, zPredict, normal []float64, ramp *deck.Ramp) (z []float64, maxPow, arcResid float64, ok bool, err error)

// TangentFn computes an oriented unit tangent.
type TangentFn func(buses []grid.Bus, lay equations.Layout, y map[[2]string]complex128, demands map[string]deck.Demand, prev []float64) ([]float64, error)

// RefineResult is the critical fold point.
type RefineResult struct {
	Z           []float64
	MaxMismatch float64
	ArcResidual float64
}

// Refine is unavailable in the starter boundary.
func Refine(
	buses []grid.Bus,
	lay equations.Layout,
	y map[[2]string]complex128,
	demands map[string]deck.Demand,
	br Bracket,
	ramp *deck.Ramp,
	correct CorrectFn,
	tangent TangentFn,
) (RefineResult, error) {
	_ = buses
	_ = lay
	_ = y
	_ = demands
	_ = br
	_ = ramp
	_ = correct
	_ = tangent
	return RefineResult{}, fmt.Errorf("scientific model unavailable: fold refinement")
}
