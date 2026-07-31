package l2anvil

import (
	"fmt"
	"math"
	"sort"
)

// Sample is one training row.
type Sample struct {
	BoutID string
	X      []int
	Y      int
}

// Fit solves intercept-aware L2 ridge and returns milliwights length 13.
func Fit(samples []Sample, lambda int) ([]int, []string, error) {
	if lambda < 1 {
		return nil, nil, fmt.Errorf("ridge_lambda must be >= 1")
	}
	sorted := append([]Sample(nil), samples...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].BoutID < sorted[j].BoutID })
	n := len(sorted)
	if n == 0 {
		return nil, nil, fmt.Errorf("no training samples")
	}
	dim := 13
	xtx := make([][]float64, dim)
	for i := range xtx {
		xtx[i] = make([]float64, dim)
	}
	xty := make([]float64, dim)
	ids := make([]string, 0, n)
	for _, s := range sorted {
		if len(s.X) != 12 {
			return nil, nil, fmt.Errorf("feature dim mismatch for %s", s.BoutID)
		}
		row := make([]float64, dim)
		row[0] = 1
		for i := 0; i < 12; i++ {
			row[i+1] = float64(s.X[i])
		}
		y := float64(s.Y)
		for i := 0; i < dim; i++ {
			xty[i] += row[i] * y
			for j := 0; j < dim; j++ {
				xtx[i][j] += row[i] * row[j]
			}
		}
		ids = append(ids, s.BoutID)
	}
	for i := 0; i < dim; i++ {
		xtx[i][i] += float64(lambda)
	}
	w, err := solve(xtx, xty)
	if err != nil {
		return nil, nil, err
	}
	milli := make([]int, dim)
	for i := range w {
		milli[i] = int(math.Round(w[i] * 1000))
	}
	return milli, ids, nil
}

// ScoreMilli returns w·[1000, 1000*x...] as integer milli-score * 1000? 
// Spec: s_milli = w_milli · [1000, 1000*x0, ...] then s = s_milli / 1_000_000
func ScoreMilli(wMilli []int, x []int) int64 {
	var acc int64
	acc += int64(wMilli[0]) * 1000
	for i := 0; i < 12; i++ {
		acc += int64(wMilli[i+1]) * int64(1000*x[i])
	}
	return acc
}

func Predict(wMilli []int, x []int, thresholdMilli int) (yhat int, scoreMilli int) {
	sMilli := ScoreMilli(wMilli, x)
	// s = sMilli / 1_000_000; compare to 0.5 => sMilli >= 500_000
	thr := int64(thresholdMilli) * 1000 // 500 -> 500000
	yhat = 0
	if sMilli >= thr {
		yhat = 1
	}
	// report score_milli as floor(s * 1000) = floor(sMilli / 1000)
	return yhat, int(sMilli / 1000)
}

func solve(a [][]float64, b []float64) ([]float64, error) {
	n := len(b)
	m := make([][]float64, n)
	for i := 0; i < n; i++ {
		m[i] = make([]float64, n+1)
		copy(m[i], a[i])
		m[i][n] = b[i]
	}
	for col := 0; col < n; col++ {
		pivot := col
		best := math.Abs(m[col][col])
		for r := col + 1; r < n; r++ {
			if v := math.Abs(m[r][col]); v > best {
				best = v
				pivot = r
			}
		}
		if best < 1e-15 {
			return nil, fmt.Errorf("singular ridge system")
		}
		m[col], m[pivot] = m[pivot], m[col]
		div := m[col][col]
		for c := col; c <= n; c++ {
			m[col][c] /= div
		}
		for r := 0; r < n; r++ {
			if r == col {
				continue
			}
			factor := m[r][col]
			for c := col; c <= n; c++ {
				m[r][c] -= factor * m[col][c]
			}
		}
	}
	out := make([]float64, n)
	for i := 0; i < n; i++ {
		out[i] = m[i][n]
	}
	return out, nil
}
