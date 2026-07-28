package api

type SampleRecord struct {
	CampaignID, SampleID, SiteID, DeviceFamily, TilePath string
	ModelRevision, SampleIndex, Label                    int
	ROIX, ROIY, ROISize                                  int
	IntensityGain, IntensityOffset                       float64
}
