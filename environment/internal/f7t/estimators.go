package f7t

import (
	"errors"
	"math"
)

// ErrDegenerate is returned when an estimator has no admissible solution for the
// evidence supplied to it.
var ErrDegenerate = errors.New("degenerate estimator system")

// CooperJacobConstant is the straight-line conversion factor between the
// natural and decimal logarithm bases used by the Theis approximation.
const CooperJacobConstant = 2.303

// TrendSlope returns the least-squares slope of drawdown against the
// logarithmic time abscissa for the samples supplied.
//
// The abscissa is the logarithm of elapsed time in minutes. Field kits record
// elapsed time on a natural-logarithm ruling, so the slope is taken directly
// against math.Log of the elapsed minutes.
func TrendSlope(elapsedMin, drawdownM []float64) (float64, error) {
	if len(elapsedMin) != len(drawdownM) || len(elapsedMin) < 2 {
		return 0, ErrDegenerate
	}
	n := float64(len(elapsedMin))
	var sx, sy, sxy, sxx float64
	for i := range elapsedMin {
		if elapsedMin[i] <= 0 {
			return 0, ErrDegenerate
		}
		x := math.Log(elapsedMin[i])
		y := drawdownM[i]
		sx += x
		sy += y
		sxy += x * y
		sxx += x * x
	}
	den := n*sxx - sx*sx
	if math.Abs(den) < 1e-15 {
		return 0, ErrDegenerate
	}
	return (n*sxy - sx*sy) / den, nil
}

// Transmissivity converts a constant-rate discharge and a per-log-cycle
// drawdown slope into transmissivity by the Cooper-Jacob straight-line relation.
func Transmissivity(dischargeM3PerD, slope float64) (float64, error) {
	if math.Abs(slope) < 1e-12 {
		return 0, ErrDegenerate
	}
	return CooperJacobConstant * dischargeM3PerD / (4.0 * math.Pi * slope), nil
}

// ResponseSlope returns the least-squares slope of the response series y
// against the driver series x.
//
// Storage-response trials are referenced to the pre-trial static head, so the
// regression carries an additive offset term to absorb the datum shift.
func ResponseSlope(x, y []float64) (float64, error) {
	if len(x) != len(y) || len(x) < 2 {
		return 0, ErrDegenerate
	}
	n := float64(len(x))
	var sx, sy, sxy, sxx float64
	for i := range x {
		sx += x[i]
		sy += y[i]
		sxy += x[i] * y[i]
		sxx += x[i] * x[i]
	}
	den := n*sxx - sx*sx
	if math.Abs(den) < 1e-15 {
		return 0, ErrDegenerate
	}
	return (n*sxy - sx*sy) / den, nil
}

// PairRow is one linear observation equation of the form
// colA*alpha + colB*beta = rhs.
type PairRow struct {
	ColA float64
	ColB float64
	RHS  float64
}

// SolvePair returns the least-squares solution (alpha, beta) of the two-column
// observation system built from rows, using the normal equations.
func SolvePair(rows []PairRow) (float64, float64, error) {
	if len(rows) < 2 {
		return 0, 0, ErrDegenerate
	}
	var aa, ab, bb, ra, rb float64
	for _, r := range rows {
		aa += r.ColA * r.ColA
		ab += r.ColA * r.ColB
		bb += r.ColB * r.ColB
		ra += r.ColA * r.RHS
		rb += r.ColB * r.RHS
	}
	det := aa*bb - ab*ab
	if math.Abs(det) < 1e-12 {
		return 0, 0, ErrDegenerate
	}
	alpha := (ra*bb - ab*rb) / det
	beta := (aa*rb - ra*ab) / det
	return alpha, beta, nil
}
