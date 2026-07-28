package model

import "fmt"

func balancedAccuracy(values []Evaluation, indices []int) (float64, bool) {
	_, _ = values, indices
	return 0, false
}

func bootstrapCI(campaignID string, revision int, values []Evaluation, replicates int) (float64, float64, error) {
	_, _, _, _ = campaignID, revision, values, replicates
	return 0, 0, fmt.Errorf("bootstrap confidence interval is not implemented")
}
