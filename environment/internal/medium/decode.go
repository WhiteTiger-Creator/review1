package medium

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
)

type wireConfig struct {
	SchemaVersion   int         `json:"schema_version"`
	MixingAngleRad  float64     `json:"mixing_angle_rad"`
	DeltaM2EV2      float64     `json:"delta_m2_ev2"`
	MaxPhaseStepRad *float64    `json:"max_phase_step_rad,omitempty"`
	EnergiesGEV     []float64   `json:"energies_gev"`
	Layers          []wireLayer `json:"layers"`
}

type wireLayer struct {
	LengthKM         float64  `json:"length_km"`
	DensityGCM3      *float64 `json:"density_g_cm3,omitempty"`
	DensityStartGCM3 *float64 `json:"density_start_g_cm3,omitempty"`
	DensityEndGCM3   *float64 `json:"density_end_g_cm3,omitempty"`
	ElectronFraction float64  `json:"electron_fraction"`
}

func Load(path string) (Config, []byte, string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Config{}, nil, "", err
	}
	var wire wireConfig
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&wire); err != nil {
		return Config{}, nil, "", fmt.Errorf("invalid config: %w", err)
	}
	if err := requireEOF(dec); err != nil {
		return Config{}, nil, "", fmt.Errorf("invalid config: %w", err)
	}
	cfg, err := normalize(wire)
	if err != nil {
		return Config{}, nil, "", err
	}
	return cfg, raw, ExactSHA256(raw), nil
}

func requireEOF(dec *json.Decoder) error {
	var extra any
	err := dec.Decode(&extra)
	if err == io.EOF {
		return nil
	}
	if err == nil {
		return fmt.Errorf("trailing JSON value")
	}
	return err
}

func normalize(w wireConfig) (Config, error) {
	cfg := Config{
		SchemaVersion:  w.SchemaVersion,
		MixingAngleRad: w.MixingAngleRad,
		DeltaM2EV2:     w.DeltaM2EV2,
		EnergiesGEV:    append([]float64(nil), w.EnergiesGEV...),
		SingleStep:     w.SchemaVersion == 1,
	}
	switch w.SchemaVersion {
	case 1:
		if w.MaxPhaseStepRad != nil {
			return Config{}, invalid("schema 1 must not contain max_phase_step_rad")
		}
		cfg.MaxPhaseStepRad = 0
	case 2:
		if w.MaxPhaseStepRad == nil {
			return Config{}, invalid("schema 2 requires max_phase_step_rad")
		}
		cfg.MaxPhaseStepRad = *w.MaxPhaseStepRad
	default:
		return Config{}, invalid("schema_version must be 1 or 2")
	}
	cfg.Layers = make([]Layer, len(w.Layers))
	for i, layer := range w.Layers {
		out := Layer{LengthKM: layer.LengthKM, ElectronFraction: layer.ElectronFraction}
		if w.SchemaVersion == 1 {
			if layer.DensityGCM3 == nil || layer.DensityStartGCM3 != nil || layer.DensityEndGCM3 != nil {
				return Config{}, invalidf("layer %d must use density_g_cm3 only", i)
			}
			out.DensityStartGCM3 = *layer.DensityGCM3
			out.DensityEndGCM3 = *layer.DensityGCM3
		} else {
			if layer.DensityGCM3 != nil || layer.DensityStartGCM3 == nil || layer.DensityEndGCM3 == nil {
				return Config{}, invalidf("layer %d must use density_start_g_cm3 and density_end_g_cm3", i)
			}
			out.DensityStartGCM3 = *layer.DensityStartGCM3
			out.DensityEndGCM3 = *layer.DensityEndGCM3
		}
		cfg.Layers[i] = out
	}
	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}
