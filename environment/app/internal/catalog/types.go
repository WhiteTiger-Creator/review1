package catalog

type Sample struct {
	Index           int     `json:"sample_index"`
	ID              string  `json:"sample_id"`
	SiteID          string  `json:"site_id"`
	DeviceFamily    string  `json:"device_family"`
	Label           int     `json:"label"`
	TilePath        string  `json:"tile_path"`
	ROIX            int     `json:"roi_x"`
	ROIY            int     `json:"roi_y"`
	ROISize         int     `json:"roi_size"`
	IntensityGain   float64 `json:"intensity_gain"`
	IntensityOffset float64 `json:"intensity_offset"`
}

type Head struct {
	ID            string    `json:"head_id"`
	Order         int       `json:"head_order"`
	Intercept     float64   `json:"intercept"`
	Temperature   float64   `json:"temperature"`
	VoteWeight    float64   `json:"vote_weight"`
	Weights       []float64 `json:"weights"`
	WeightIndices []int     `json:"weight_indices"`
}

type FeatureReference struct {
	Index int     `json:"feature_index"`
	Name  string  `json:"feature_name"`
	Mean  float64 `json:"mean"`
	Scale float64 `json:"scale"`
}

type Campaign struct {
	ID                       string             `json:"campaign_id"`
	ModelRevision            int                `json:"model_revision"`
	FeatureRevision          string             `json:"feature_revision"`
	ExpectedSampleCount      int                `json:"expected_sample_count"`
	FeatureCount             int                `json:"feature_count"`
	DecisionThreshold        float64            `json:"decision_threshold"`
	AbstainSpread            float64            `json:"abstain_spread"`
	BootstrapReplicates      int                `json:"bootstrap_replicates"`
	ECEBins                  int                `json:"ece_bins"`
	MinCoverage              float64            `json:"min_coverage"`
	MinBalancedAccuracyLower float64            `json:"min_balanced_accuracy_lower"`
	MaxBrier                 float64            `json:"max_brier"`
	MaxECE                   float64            `json:"max_ece"`
	MaxFPRGap                float64            `json:"max_fpr_gap"`
	MaxFeatureDrift          float64            `json:"max_feature_drift"`
	Samples                  []Sample           `json:"samples"`
	Heads                    []Head             `json:"heads"`
	FeatureReferences        []FeatureReference `json:"feature_references"`
}
