package arc

import (
	"fmt"

	"loadcrest/internal/deck"
	"loadcrest/internal/equations"
	"loadcrest/internal/grid"
)

// CorrectResult is one corrector attempt.
type CorrectResult struct {
	Z          []float64
	Iterations int
	MaxPower   float64
	ArcResid   float64
	OK         bool
}

// Correct is unavailable in the starter boundary.
func Correct(
	buses []grid.Bus,
	lay equations.Layout,
	y map[[2]string]complex128,
	demands map[string]deck.Demand,
	zPredict, t []float64,
	ramp *deck.Ramp,
) (CorrectResult, error) {
	_ = buses
	_ = lay
	_ = y
	_ = demands
	_ = zPredict
	_ = t
	_ = ramp
	return CorrectResult{}, fmt.Errorf("scientific model unavailable: corrector")
}
