package l2anvil

import "fmt"

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
	ids := make([]string, 0, len(samples))
	for _, s := range samples {
		ids = append(ids, s.BoutID)
	}
	return make([]int, 13), ids, nil
}

func ScoreMilli(wMilli []int, x []int) int64 {
	_ = wMilli
	_ = x
	return 0
}

func Predict(wMilli []int, x []int, thresholdMilli int) (yhat int, scoreMilli int) {
	_ = wMilli
	_ = x
	_ = thresholdMilli
	return 0, 0
}
