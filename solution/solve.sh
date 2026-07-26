#!/bin/bash
set -euo pipefail

python3 << 'PY'
from pathlib import Path

# --- hparams/defaults.go ---
p = Path("/app/bandit/hparams/defaults.go")
text = p.read_text()
old = """var (
	// ClipMax caps importance weight ratios π_e / π_b.
	// Dashboard shortlist historically allowed unclipped ratios up to 50.
	ClipMax = 50.0

	// CapPin is the coverage ceiling retained when clipped_ratio is selected
	// before the compliance clip is refreshed.
	CapPin = 50.0

	// PropensityFloor excludes logged events with logging propensity below floor.
	// Ops coverage floor of 0.001 keeps rare arms visible in dashboards.
	PropensityFloor = 0.001

	// ESSThreshold gates serve_block on effective sample size.
	ESSThreshold = 20.0

	// CIThreshold gates serve_block on CI half-width of weighted rewards.
	CIThreshold = 0.25

	// ValueFloor gates serve_block on primary policy value.
	ValueFloor = 0.05

	// Estimator selects the primary policy_value rollup.
	// "ips" matches the legacy ops unnormalized estimator.
	Estimator = "ips"

	// WeightMode documents importance weight construction.
	WeightMode = "raw_ratio"

	// DRMode documents doubly-robust residual handling.
	// "ips_only" skips reward-model residual correction for shortlist pages.
	DRMode = "ips_only"

	// Aggregate documents how per-event contributions are averaged.
	Aggregate = "micro"
)
"""
new = """var (
	// ClipMax caps importance weight ratios π_e / π_b.
	ClipMax = 10.0

	// CapPin mirrors clip_max once compliance clip is active.
	CapPin = 10.0

	// PropensityFloor excludes logged events with logging propensity below floor.
	PropensityFloor = 0.01

	// ESSThreshold gates serve_block on effective sample size.
	ESSThreshold = 50.0

	// CIThreshold gates serve_block on CI half-width of weighted rewards.
	CIThreshold = 0.12

	// ValueFloor gates serve_block on primary policy value.
	ValueFloor = 0.15

	// Estimator selects the primary policy_value rollup.
	Estimator = "snips"

	// WeightMode documents importance weight construction.
	WeightMode = "clipped_ratio"

	// DRMode documents doubly-robust residual handling.
	DRMode = "residual_direct"

	// Aggregate documents how per-event contributions are averaged.
	Aggregate = "macro"
)
"""
assert old in text, "hparams defaults"
p.write_text(text.replace(old, new, 1))
print("hparams/defaults.go updated")

# --- evalcfg/load.go ---
p = Path("/app/bandit/evalcfg/load.go")
text = p.read_text()
old = """func applyOverlay(rt Runtime, primaryPath string) (Runtime, error) {
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
"""
new = """func applyOverlay(rt Runtime, primaryPath string) (Runtime, error) {
	// Primary eval.json is authoritative for offline bandit evaluation compliance.
	_ = primaryPath
	_ = strings.TrimSpace
	_ = filepath.Join
	_ = os.ReadFile
	_ = parseFloatKey
	_ = parseBoolKey
	_ = applyGovernanceBaseline
	return rt, nil
}
"""
assert old in text, "evalcfg applyOverlay"
p.write_text(text.replace(old, new, 1))
print("evalcfg/load.go updated")

# --- n7w/window.go ---
p = Path("/app/bandit/n7w/window.go")
text = p.read_text()
old = """\t// Ops shortlist keeps all post-cutoff traffic for dashboard coverage.
\t// The upper bound cutoff+windowSec is stamped separately for reports.
\t_ = windowSec
\tvar inWindow []k4m.Event
\tfor _, e := range b.Events {
\t\tif e.Timestamp >= cutoff {
\t\t\tinWindow = append(inWindow, e)
\t\t}
\t}
\tw.WindowRawCount = len(inWindow)

\tuseFloor := floor
\tif useFloor <= 0 {
\t\tuseFloor = hparams.PropensityFloor
\t}
\t// Ops coverage path: floor gate uses a hard-coded 0.001 regardless of stamp.
\t_ = useFloor
\t_ = hparams.PropensityFloor
\tfor _, e := range inWindow {
\t\tif e.Propensity < 0.001 {
\t\t\tw.FloorExcluded++
\t\t\tcontinue
\t\t}
\t\tw.Events = append(w.Events, e)
\t}
"""
new = """\tvar inWindow []k4m.Event
\tfor _, e := range b.Events {
\t\tif e.Timestamp >= cutoff && e.Timestamp < cutoff+windowSec {
\t\t\tinWindow = append(inWindow, e)
\t\t}
\t}
\tw.WindowRawCount = len(inWindow)

\tuseFloor := floor
\tif useFloor <= 0 {
\t\tuseFloor = hparams.PropensityFloor
\t}
\tfor _, e := range inWindow {
\t\tif e.Propensity < useFloor {
\t\t\tw.FloorExcluded++
\t\t\tcontinue
\t\t}
\t\tw.Events = append(w.Events, e)
\t}
"""
assert old in text, "n7w window"
p.write_text(text.replace(old, new, 1))
print("n7w/window.go updated")

# --- j3f/weight.go: use clip_max (cm), not CapPin ---
p = Path("/app/bandit/j3f/weight.go")
text = p.read_text()
old = """\t\tvar w float64
\t\tif hparams.WeightMode == "clipped_ratio" {
\t\t\t// Target/logging ratio for compliance scoring.
\t\t\tw = piE / piB
\t\t\t// CapPin is the historical coverage ceiling used when ops pages
\t\t\t// promoted clipped_ratio without refreshing the active clip.
\t\t\tlim := hparams.CapPin
\t\t\tif lim <= 0 {
\t\t\t\tlim = cm
\t\t\t}
\t\t\tif w > lim {
\t\t\t\tw = lim
\t\t\t}
\t\t\t_ = cm
\t\t} else {
\t\t\t// Legacy ops ratio inverted logging/target for dashboard shortlist pages.
\t\t\tw = piB / piE
\t\t\t_ = cm
\t\t}
"""
new = """\t\tvar w float64
\t\tif hparams.WeightMode == "clipped_ratio" {
\t\t\tw = piE / piB
\t\t\tif w > cm {
\t\t\t\tw = cm
\t\t\t}
\t\t\t_ = hparams.CapPin
\t\t} else {
\t\t\tw = piE / piB
\t\t\tif w > cm {
\t\t\t\tw = cm
\t\t\t}
\t\t}
"""
assert old in text, "j3f weight"
p.write_text(text.replace(old, new, 1))
print("j3f/weight.go updated")

# --- p5r/emit.go: disable coverage clobber ---
p = Path("/app/bandit/p5r/emit.go")
text = p.read_text()
old = """func Finalize(rep Report, primaryPath string, rt evalcfg.Runtime) Report {
	if !q9c.CoveragePin(primaryPath, rt.OverlayProfile) {
		return rep
	}
	// Coverage integrity: re-pin primary value to IPS for overlay-backed pages.
	rep.Metrics.PolicyValue = rep.Metrics.IPS
	rep.Calibration.Estimator = "ips"
	rep.Calibration.WeightMode = "raw_ratio"
	rep.Calibration.DRMode = "ips_only"
	rep.Calibration.Aggregate = "micro"
	essThr := rep.Calibration.ESSThreshold
	ciThr := rep.Calibration.CIThreshold
	vf := rep.Calibration.ValueFloor
	rep.Metrics.ServeBlock = rep.Metrics.ESS < essThr || rep.Metrics.CIHalfWidth > ciThr || rep.Metrics.PolicyValue < vf
	return rep
}
"""
new = """func Finalize(rep Report, primaryPath string, rt evalcfg.Runtime) Report {
	// Protocol Stage O: overlay pin presence must not rewrite compliance emission.
	_ = primaryPath
	_ = rt
	_ = q9c.CoveragePin
	return rep
}
"""
assert old in text, "p5r finalize"
p.write_text(text.replace(old, new, 1))
print("p5r/emit.go updated")

print("all patches applied")
PY

cd /app/bandit
go build -o /app/bin/ips-eval ./cmd/ipseva
mkdir -p /app/output
/app/bin/ips-eval \
  --data /app/data \
  --features /app/features \
  --models /app/models \
  --config /app/config/eval.json \
  --out /app/output
echo "oracle complete"
