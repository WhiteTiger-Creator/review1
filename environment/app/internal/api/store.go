package api

import (
	"context"
	"errors"
	"fmt"
	"orbit.local/sentinel/internal/catalog"
)

var ErrSampleNotFound = errors.New("sample not found")

type sampleKey struct {
	campaign string
	index    int
}
type Store struct {
	samples   map[sampleKey]SampleRecord
	campaigns map[string]int
}

func OpenStore(path string) (*Store, error) {
	campaigns, err := catalog.Load(context.Background(), path)
	if err != nil {
		return nil, err
	}
	store := &Store{samples: map[sampleKey]SampleRecord{}, campaigns: map[string]int{}}
	for _, campaign := range campaigns {
		store.campaigns[campaign.ID] = campaign.ModelRevision
		for _, sample := range campaign.Samples {
			key := sampleKey{campaign: campaign.ID, index: sample.Index}
			store.samples[key] = SampleRecord{CampaignID: campaign.ID, SampleID: sample.ID, SiteID: sample.SiteID, DeviceFamily: sample.DeviceFamily, TilePath: sample.TilePath, ModelRevision: campaign.ModelRevision, SampleIndex: sample.Index, Label: sample.Label, ROIX: sample.ROIX, ROIY: sample.ROIY, ROISize: sample.ROISize, IntensityGain: sample.IntensityGain, IntensityOffset: sample.IntensityOffset}
		}
	}
	return store, nil
}
func (s *Store) Close() error { return nil }
func (s *Store) Sample(ctx context.Context, campaign string, index int) (SampleRecord, error) {
	if err := ctx.Err(); err != nil {
		return SampleRecord{}, err
	}
	record, ok := s.samples[sampleKey{campaign: campaign, index: index}]
	if !ok {
		return SampleRecord{}, ErrSampleNotFound
	}
	return record, nil
}
func (s *Store) Revision(campaign string) (int, error) {
	revision, ok := s.campaigns[campaign]
	if !ok {
		return 0, fmt.Errorf("campaign not found")
	}
	return revision, nil
}
