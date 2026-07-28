package model

import (
	"fmt"
	"orbit.local/sentinel/internal/catalog"
)

func Infer(campaign catalog.Campaign, sample catalog.Sample, features []float64, etag string) (Evaluation, error) {
	_, _, _, _ = campaign, sample, features, etag
	return Evaluation{}, fmt.Errorf("ensemble inference is not implemented")
}
