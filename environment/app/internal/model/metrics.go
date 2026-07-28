package model

import (
	"fmt"
	"orbit.local/sentinel/internal/catalog"
)

func Compute(campaign catalog.Campaign, values []Evaluation) (Metrics, error) {
	_, _ = campaign, values
	return Metrics{}, fmt.Errorf("release metrics are not implemented")
}
