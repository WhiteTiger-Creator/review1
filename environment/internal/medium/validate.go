package medium

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"math"
	"sort"
)

func (c *Config) Validate() error {
	if !finite(c.MixingAngleRad) || c.MixingAngleRad <= 0 || c.MixingAngleRad >= math.Pi/2 {
		return invalid("mixing_angle_rad must be finite and between 0 and pi/2")
	}
	if !finite(c.DeltaM2EV2) || c.DeltaM2EV2 <= 0 {
		return invalid("delta_m2_ev2 must be finite and positive")
	}
	if c.SchemaVersion == 2 && (!finite(c.MaxPhaseStepRad) || c.MaxPhaseStepRad <= 0 || c.MaxPhaseStepRad > math.Pi) {
		return invalid("max_phase_step_rad must be finite, positive, and at most pi")
	}
	if len(c.EnergiesGEV) == 0 {
		return invalid("energies_gev must not be empty")
	}
	sort.Float64s(c.EnergiesGEV)
	for i, energy := range c.EnergiesGEV {
		if !finite(energy) || energy <= 0 {
			return invalid("every energy must be finite and positive")
		}
		if i > 0 && energy == c.EnergiesGEV[i-1] {
			return invalid("duplicate energies are not allowed")
		}
	}
	for i, layer := range c.Layers {
		if !finite(layer.LengthKM) || layer.LengthKM < 0 {
			return invalidf("layer %d length must be finite and non-negative", i)
		}
		if !finite(layer.DensityStartGCM3) || layer.DensityStartGCM3 < 0 || !finite(layer.DensityEndGCM3) || layer.DensityEndGCM3 < 0 {
			return invalidf("layer %d densities must be finite and non-negative", i)
		}
		if !finite(layer.ElectronFraction) || layer.ElectronFraction < 0 || layer.ElectronFraction > 1 {
			return invalidf("layer %d electron_fraction must be between 0 and 1", i)
		}
	}
	return nil
}

func ExactSHA256(raw []byte) string {
	sum := sha256.Sum256(bytes.TrimSpace(raw))
	return hex.EncodeToString(sum[:])
}

func finite(v float64) bool        { return !math.IsNaN(v) && !math.IsInf(v, 0) }
func invalid(message string) error { return errors.New("invalid config: " + message) }
func invalidf(format string, args ...any) error {
	return fmt.Errorf("invalid config: "+format, args...)
}
