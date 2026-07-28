package analysis

type Tile struct {
	Width, Height int
	Pixels        []float64
}

type Features struct{ Values []float64 }

var FeatureNames = []string{"mean_intensity", "std_intensity", "radial_log_1", "radial_log_2", "radial_log_3", "radial_log_4", "radial_log_5", "radial_log_6", "high_low_ratio"}
