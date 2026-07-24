package basepoint

import (
	"fmt"

	"loadcrest/internal/deck"
	"loadcrest/internal/equations"
	"loadcrest/internal/grid"
)

// Solve reports that the zero-loading Newton model is unavailable.
func Solve(buses []grid.Bus, y map[[2]string]complex128, demands map[string]deck.Demand, ramp *deck.Ramp) (equations.Layout, int, error) {
	_ = buses
	_ = y
	_ = demands
	_ = ramp
	return equations.Layout{}, 0, fmt.Errorf("scientific model unavailable: base-point Newton solve")
}
