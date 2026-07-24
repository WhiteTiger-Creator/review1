package medium

type Layer struct {
	LengthKM         float64
	DensityStartGCM3 float64
	DensityEndGCM3   float64
	ElectronFraction float64
}

type Config struct {
	SchemaVersion   int
	MixingAngleRad  float64
	DeltaM2EV2      float64
	MaxPhaseStepRad float64
	EnergiesGEV     []float64
	Layers          []Layer
	SingleStep      bool
}
