package publish

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type UttRow struct {
	UttID    string  `json:"utt_id"`
	Fold     string  `json:"fold"`
	Score    float64 `json:"score"`
	Conf     float64 `json:"conf"`
	Accepted bool    `json:"accepted"`
	Y        int     `json:"y"`
}

type Report struct {
	SchemaRev      int      `json:"schema_rev"`
	CampaignID     string   `json:"campaign_id"`
	PackDigest     string   `json:"pack_digest"`
	PolicyDigest   string   `json:"policy_digest"`
	EmbedDigest    string   `json:"embed_digest"`
	BundleDigest   string   `json:"bundle_digest"`
	Temperature    float64  `json:"temperature"`
	Threshold      float64  `json:"threshold"`
	CalibCoverage  float64  `json:"calib_coverage"`
	CalibRisk      float64  `json:"calib_risk"`
	EvalCoverage   float64  `json:"eval_coverage"`
	EvalRisk       float64  `json:"eval_risk"`
	Utterances     []UttRow `json:"utterances"`
}

type State struct {
	SchemaRev    int     `json:"schema_rev"`
	CampaignID   string  `json:"campaign_id"`
	Epoch        int     `json:"epoch"`
	PackDigest   string  `json:"pack_digest"`
	PolicyDigest string  `json:"policy_digest"`
	EmbedDigest  string  `json:"embed_digest"`
	BundleDigest string  `json:"bundle_digest"`
	Temperature  float64 `json:"temperature"`
	Threshold    float64 `json:"threshold"`
	EvalCoverage float64 `json:"eval_coverage"`
	EvalRisk     float64 `json:"eval_risk"`
}

type Hist struct {
	Epoch        int     `json:"epoch"`
	CampaignID   string  `json:"campaign_id"`
	BundleDigest string  `json:"bundle_digest"`
	Temperature  float64 `json:"temperature"`
	Threshold    float64 `json:"threshold"`
	EvalCoverage float64 `json:"eval_coverage"`
	EvalRisk     float64 `json:"eval_risk"`
	Status       string  `json:"status"`
}

func ClearPrimary(outDir string) {
	for _, n := range []string{
		"align_report.json",
		"utterance_scores.csv",
		"eval_summary.log",
		"campaign_state.json",
	} {
		_ = os.Remove(filepath.Join(outDir, n))
	}
}

func WriteAll(outDir, varDir string, rep Report, st State, hist Hist) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	if err := os.MkdirAll(varDir, 0o755); err != nil {
		return err
	}
	jb, err := json.MarshalIndent(rep, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(outDir, "align_report.json"), jb, 0o644); err != nil {
		return err
	}
	var csv strings.Builder
	csv.WriteString("utt_id,fold,score,conf,accepted,y\n")
	for _, u := range rep.Utterances {
		acc := 0
		if u.Accepted {
			acc = 1
		}
		csv.WriteString(fmt.Sprintf("%s,%s,%.6f,%.6f,%d,%d\n", u.UttID, u.Fold, u.Score, u.Conf, acc, u.Y))
	}
	if err := os.WriteFile(filepath.Join(outDir, "utterance_scores.csv"), []byte(csv.String()), 0o644); err != nil {
		return err
	}
	log := fmt.Sprintf(
		"CAMPAIGN=%s\nTEMPERATURE=%.4f\nTHRESHOLD=%.4f\nEVAL_COVERAGE=%.6f\nEVAL_RISK=%.6f\nBUNDLE_DIGEST=%s\nEPOCH=%d\n",
		rep.CampaignID, rep.Temperature, rep.Threshold, rep.EvalCoverage, rep.EvalRisk, rep.BundleDigest, st.Epoch,
	)
	if err := os.WriteFile(filepath.Join(outDir, "eval_summary.log"), []byte(log), 0o644); err != nil {
		return err
	}
	sb, err := json.MarshalIndent(st, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(outDir, "campaign_state.json"), sb, 0o644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(varDir, "chironym_state.json"), sb, 0o644); err != nil {
		return err
	}
	hb, err := json.Marshal(hist)
	if err != nil {
		return err
	}
	hf := filepath.Join(outDir, "risk_history.jsonl")
	f, err := os.OpenFile(hf, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	if _, err := f.Write(append(hb, '\n')); err != nil {
		return err
	}
	return nil
}
