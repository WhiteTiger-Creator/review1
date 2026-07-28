package model

import "orbit.local/sentinel/internal/catalog"

type Evaluation struct {
	Sample      catalog.Sample
	Features    []float64
	Probability float64
	Uncertainty float64
	Abstained   bool
	Prediction  int
	ETag        string
}

type Cohort struct {
	SiteID             string
	Count              int
	Coverage, TPR, FPR float64
}
type Drift struct {
	Index                              int
	Name                               string
	ObservedMean, ReferenceMean, Score float64
}
type Metrics struct {
	Coverage, BalancedAccuracy, Brier, ECE, FPRGap, MaxFeatureDrift float64
	CILow, CIHigh                                                   float64
	Cohorts                                                         []Cohort
	Drift                                                           []Drift
}
