package catalog

import (
	"context"
	"fmt"
	"orbit.local/sentinel/internal/registrybridge"
)

type exportEnvelope struct {
	Campaigns []Campaign `json:"campaigns"`
}

func Load(ctx context.Context, path string) ([]Campaign, error) {
	var envelope exportEnvelope
	if err := registrybridge.Export(ctx, path, &envelope); err != nil {
		return nil, err
	}
	if len(envelope.Campaigns) == 0 {
		return nil, fmt.Errorf("catalog has no published campaigns")
	}
	for index := range envelope.Campaigns {
		if err := Validate(envelope.Campaigns[index]); err != nil {
			return nil, fmt.Errorf("campaign %q: %w", envelope.Campaigns[index].ID, err)
		}
	}
	return envelope.Campaigns, nil
}
