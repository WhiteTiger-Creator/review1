package equations

import (
	"loadcrest/internal/grid"
	"loadcrest/internal/linear"
)

// AnalyticJacobian is unavailable in the starter boundary.
func AnalyticJacobian(buses []grid.Bus, lay Layout, y map[[2]string]complex128) *linear.Matrix {
	_ = buses
	_ = y
	n := lay.Dim()
	if n == 0 {
		return linear.NewMatrix(1)
	}
	return linear.NewMatrix(n)
}
