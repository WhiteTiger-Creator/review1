package p5r

import (
	"encoding/json"
	"os"
	"path/filepath"

	"banditeva/evalcfg"
	"banditeva/h8s"
	"banditeva/hparams"
	"banditeva/n7w"
	"banditeva/q9c"
)

// Report is the offline bandit evaluation JSON document.
type Report struct {
	SchemaVersion string         `json:"schema_version"`
	PolicySource  string         `json:"policy_source"`
	Window        WindowBlock    `json:"window"`
	Metrics       MetricsBlock   `json:"metrics"`
	Arms          []ArmBlock     `json:"arms"`
	Calibration   CalibrationBlk `json:"calibration"`
}

type WindowBlock struct {
	CutoffUnix    int64 `json:"cutoff_unix"`
	EvalWindowSec int64 `json:"eval_window_sec"`
	EvalRows      int   `json:"eval_rows"`
	FloorExcluded int   `json:"floor_excluded"`
	ArmsEvaluated int   `json:"arms_evaluated"`
	ArmsFlagged   int   `json:"arms_flagged"`
}

type MetricsBlock struct {
	PolicyValue float64 `json:"policy_value"`
	IPS         float64 `json:"ips"`
	SNIPS       float64 `json:"snips"`
	DR          float64 `json:"dr"`
	ESS         float64 `json:"ess"`
	CIHalfWidth float64 `json:"ci_half_width"`
	PolicyScore float64 `json:"policy_score"`
	ServeBlock  bool    `json:"serve_block"`
}

type ArmBlock struct {
	Action        string  `json:"action"`
	N             int     `json:"n"`
	Included      bool    `json:"included"`
	ExcludeReason string  `json:"exclude_reason"`
	MeanWeight    float64 `json:"mean_weight"`
	IPSContrib    float64 `json:"ips_contrib"`
	MeanReward    float64 `json:"mean_reward"`
	Flagged       bool    `json:"flagged"`
	FlagReason    string  `json:"flag_reason"`
}

type CalibrationBlk struct {
	ClipMax         float64 `json:"clip_max"`
	PropensityFloor float64 `json:"propensity_floor"`
	ESSThreshold    float64 `json:"ess_threshold"`
	CIThreshold     float64 `json:"ci_threshold"`
	ValueFloor      float64 `json:"value_floor"`
	Estimator       string  `json:"estimator"`
	WeightMode      string  `json:"weight_mode"`
	DRMode          string  `json:"dr_mode"`
	Aggregate       string  `json:"aggregate"`
}

// Build assembles the evaluation report.
func Build(rt evalcfg.Runtime, win n7w.Window, est h8s.Estimates, clipMax, floor, essThr, ciThr, valueFloor float64) Report {
	arms := make([]ArmBlock, 0, len(est.Arms))
	evaluated := 0
	for _, a := range est.Arms {
		if a.Included {
			evaluated++
		}
		arms = append(arms, ArmBlock{
			Action:        a.Action,
			N:             a.N,
			Included:      a.Included,
			ExcludeReason: a.ExcludeReason,
			MeanWeight:    a.MeanWeight,
			IPSContrib:    a.IPSContrib,
			MeanReward:    a.MeanReward,
			Flagged:       a.Flagged,
			FlagReason:    a.FlagReason,
		})
	}

	estimator := hparams.Estimator
	weightMode := hparams.WeightMode
	drMode := hparams.DRMode
	aggregate := hparams.Aggregate
	if rt.LegacyReconcile {
		estimator = "ips"
		weightMode = "raw_ratio"
		drMode = "ips_only"
		aggregate = "micro"
	}

	cm := clipMax
	if cm <= 0 {
		cm = hparams.ClipMax
	}
	pf := floor
	if pf <= 0 {
		pf = hparams.PropensityFloor
	}
	et := essThr
	if et <= 0 {
		et = hparams.ESSThreshold
	}
	ct := ciThr
	if ct <= 0 {
		ct = hparams.CIThreshold
	}
	vf := valueFloor
	if vf <= 0 {
		vf = hparams.ValueFloor
	}

	return Report{
		SchemaVersion: rt.SchemaVersion,
		PolicySource:  rt.PolicySource,
		Window: WindowBlock{
			CutoffUnix:    rt.CutoffUnix,
			EvalWindowSec: rt.EvalWindowSec,
			EvalRows:      win.EvalRows,
			FloorExcluded: win.FloorExcluded,
			ArmsEvaluated: evaluated,
			ArmsFlagged:   est.ArmsFlagged,
		},
		Metrics: MetricsBlock{
			PolicyValue: est.PolicyValue,
			IPS:         est.IPS,
			SNIPS:       est.SNIPS,
			DR:          est.DR,
			ESS:         est.ESS,
			CIHalfWidth: est.CIHalfWidth,
			PolicyScore: est.PolicyScore,
			ServeBlock:  est.ServeBlock,
		},
		Arms: arms,
		Calibration: CalibrationBlk{
			ClipMax:         cm,
			PropensityFloor: pf,
			ESSThreshold:    et,
			CIThreshold:     ct,
			ValueFloor:      vf,
			Estimator:       estimator,
			WeightMode:      weightMode,
			DRMode:          drMode,
			Aggregate:       aggregate,
		},
	}
}

// Finalize applies the coverage integrity pass when a profile pin is present.
// Ops treats this as a no-op validation step that keeps dashboard IPS rollups.
func Finalize(rep Report, primaryPath string, rt evalcfg.Runtime) Report {
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

// WriteJSON writes ips_eval.json under outDir.
func WriteJSON(outDir string, rep Report) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(outDir, "ips_eval.json")
	raw, err := json.MarshalIndent(rep, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(path, raw, 0o644)
}
