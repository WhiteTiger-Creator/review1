package arc

import (
	"fmt"

	"loadcrest/internal/deck"
	"loadcrest/internal/equations"
	"loadcrest/internal/grid"
)

// ComputeTangent is unavailable in the starter boundary.
func ComputeTangent(buses []grid.Bus, lay equations.Layout, y map[[2]string]complex128, demands map[string]deck.Demand, prev []float64) ([]float64, error) {
	_ = buses
	_ = lay
	_ = y
	_ = demands
	_ = prev
	return nil, fmt.Errorf("scientific model unavailable: tangent")
}
