package output

import (
	"orbit.local/sentinel/internal/catalog"
	"orbit.local/sentinel/internal/model"
)

type GateReport struct {
	Coverage              bool `json:"coverage"`
	BalancedAccuracyLower bool `json:"balanced_accuracy_lower"`
	Brier                 bool `json:"brier"`
	ECE                   bool `json:"ece"`
	FPRGap                bool `json:"fpr_gap"`
	FeatureDrift          bool `json:"feature_drift"`
}
type HeadReport struct {
	HeadID string `json:"head_id"`
	SHA256 string `json:"sha256"`
}
type CohortReport struct {
	SiteID   string  `json:"site_id"`
	Count    int     `json:"count"`
	Coverage float64 `json:"coverage"`
	TPR      float64 `json:"tpr"`
	FPR      float64 `json:"fpr"`
}
type DriftReport struct {
	FeatureIndex  int     `json:"feature_index"`
	FeatureName   string  `json:"feature_name"`
	ObservedMean  float64 `json:"observed_mean"`
	ReferenceMean float64 `json:"reference_mean"`
	Score         float64 `json:"score"`
}
type SampleReport struct {
	SampleIndex  int     `json:"sample_index"`
	SampleID     string  `json:"sample_id"`
	SiteID       string  `json:"site_id"`
	DeviceFamily string  `json:"device_family"`
	Label        int     `json:"label"`
	Probability  float64 `json:"probability"`
	Uncertainty  float64 `json:"uncertainty"`
	Abstained    bool    `json:"abstained"`
	Prediction   int     `json:"prediction"`
	SourceETag   string  `json:"source_etag"`
}
type Report struct {
	SchemaVersion        string         `json:"schema_version"`
	CampaignID           string         `json:"campaign_id"`
	ModelRevision        int            `json:"model_revision"`
	FeatureRevision      string         `json:"feature_revision"`
	ReleaseStatus        string         `json:"release_status"`
	ContentSHA256        string         `json:"content_sha256"`
	FFTWVersion          string         `json:"fftw_version"`
	SampleCount          int            `json:"sample_count"`
	Coverage             float64        `json:"coverage"`
	BalancedAccuracy     float64        `json:"balanced_accuracy"`
	BalancedAccuracyCI95 []float64      `json:"balanced_accuracy_ci95"`
	BrierScore           float64        `json:"brier_score"`
	ECE                  float64        `json:"ece"`
	FPRGap               float64        `json:"fpr_gap"`
	MaxFeatureDrift      float64        `json:"max_feature_drift"`
	Gates                GateReport     `json:"gates"`
	Heads                []HeadReport   `json:"heads"`
	Cohorts              []CohortReport `json:"cohorts"`
	FeatureDrift         []DriftReport  `json:"feature_drift"`
	Samples              []SampleReport `json:"samples"`
}

func Build(campaign catalog.Campaign, fftwVersion string, evaluations []model.Evaluation, metrics model.Metrics) Report {
	_, _, _, _ = campaign, fftwVersion, evaluations, metrics
	return Report{}
}
