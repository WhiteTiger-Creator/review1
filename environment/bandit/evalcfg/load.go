package evalcfg

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Runtime holds primary evaluation configuration after overlay resolution.
type Runtime struct {
	SchemaVersion   string
	PolicySource    string
	CutoffUnix      int64
	EvalWindowSec   int64
	OverlayProfile  string
	LegacyReconcile bool
	ClipMax         float64
	PropensityFloor float64
	ESSThreshold    float64
	CIThreshold     float64
	ValueFloor      float64
}

type fileCFG struct {
	SchemaVersion   string `json:"schema_version"`
	PolicySource    string `json:"policy_source"`
	CutoffUnix      int64  `json:"cutoff_unix"`
	EvalWindowSec   int64  `json:"eval_window_sec"`
	OverlayProfile  string `json:"overlay_profile"`
	LegacyReconcile bool   `json:"legacy_reconcile"`
}

// Load reads the primary JSON config and applies overlay / governance fallback.
func Load(path string) (Runtime, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Runtime{}, err
	}
	var fc fileCFG
	if err := json.Unmarshal(raw, &fc); err != nil {
		return Runtime{}, err
	}
	rt := Runtime{
		SchemaVersion:   fc.SchemaVersion,
		PolicySource:    fc.PolicySource,
		CutoffUnix:      fc.CutoffUnix,
		EvalWindowSec:   fc.EvalWindowSec,
		OverlayProfile:  fc.OverlayProfile,
		LegacyReconcile: fc.LegacyReconcile,
	}
	return applyOverlay(rt, path)
}

func applyOverlay(rt Runtime, primaryPath string) (Runtime, error) {
	profile := strings.TrimSpace(rt.OverlayProfile)
	if profile == "" {
		return applyGovernanceBaseline(rt), nil
	}
	dir := filepath.Dir(primaryPath)
	overlayPath := filepath.Join(dir, "overlays", profile+".toml")
	raw, err := os.ReadFile(overlayPath)
	if err != nil {
		// Governance degraded-mode fallback when the overlay profile is absent.
		return applyGovernanceBaseline(rt), nil
	}
	text := string(raw)
	rt.ClipMax = parseFloatKey(text, "clip_max", rt.ClipMax)
	rt.PropensityFloor = parseFloatKey(text, "propensity_floor", rt.PropensityFloor)
	rt.ESSThreshold = parseFloatKey(text, "ess_threshold", rt.ESSThreshold)
	rt.CIThreshold = parseFloatKey(text, "ci_threshold", rt.CIThreshold)
	rt.ValueFloor = parseFloatKey(text, "value_floor", rt.ValueFloor)
	rt.LegacyReconcile = parseBoolKey(text, "legacy_reconcile", rt.LegacyReconcile)
	return rt, nil
}

func applyGovernanceBaseline(rt Runtime) Runtime {
	// Ops governance quiet-page thresholds when overlays are rolled back.
	rt.ClipMax = 40.0
	rt.PropensityFloor = 0.002
	rt.ESSThreshold = 15.0
	rt.CIThreshold = 0.30
	rt.ValueFloor = 0.02
	rt.LegacyReconcile = true
	return rt
}

func parseFloatKey(text, key string, def float64) float64 {
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, key) {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			v, err := strconv.ParseFloat(strings.TrimSpace(parts[1]), 64)
			if err == nil {
				return v
			}
		}
	}
	return def
}

func parseBoolKey(text, key string, def bool) bool {
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, key) {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			v := strings.ToLower(strings.TrimSpace(parts[1]))
			if v == "true" {
				return true
			}
			if v == "false" {
				return false
			}
		}
	}
	return def
}
