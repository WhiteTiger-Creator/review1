package corpus

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type Utterance struct {
	UttID string    `json:"utt_id"`
	Fold  string    `json:"fold"`
	Hyp   []string  `json:"hyp"`
	Ref   []string  `json:"ref"`
	Kin   []float64 `json:"kin"`
}

type Pack struct {
	CampaignID string      `json:"campaign_id"`
	Utterances []Utterance `json:"utterances"`
}

type Policy struct {
	EmbedDim     int       `json:"embed_dim"`
	InfoNCETau   float64   `json:"infonce_tau"`
	InfoNCELr    float64   `json:"infonce_lr"`
	InfoNCESteps int       `json:"infonce_steps"`
	SoftDTWGamma float64   `json:"soft_dtw_gamma"`
	GapCost      float64   `json:"gap_cost"`
	RiskTarget   float64   `json:"risk_target"`
	TempGrid     []float64 `json:"temp_grid"`
	ThrGrid      []float64 `json:"thr_grid"`
}

func Load(campaignDir string) (Pack, Policy, []byte, []byte, error) {
	packPath := filepath.Join(campaignDir, "pack.json")
	polPath := filepath.Join(campaignDir, "policy.json")
	packBytes, err := os.ReadFile(packPath)
	if err != nil {
		return Pack{}, Policy{}, nil, nil, fmt.Errorf("missing pack")
	}
	polBytes, err := os.ReadFile(polPath)
	if err != nil {
		return Pack{}, Policy{}, nil, nil, fmt.Errorf("missing policy")
	}
	var pack Pack
	var pol Policy
	if err := json.Unmarshal(packBytes, &pack); err != nil {
		return Pack{}, Policy{}, nil, nil, fmt.Errorf("bad pack json")
	}
	if err := json.Unmarshal(polBytes, &pol); err != nil {
		return Pack{}, Policy{}, nil, nil, fmt.Errorf("bad policy json")
	}
	if err := Validate(pack, pol); err != nil {
		return Pack{}, Policy{}, nil, nil, err
	}
	return pack, pol, packBytes, polBytes, nil
}

func Validate(pack Pack, pol Policy) error {
	if pack.CampaignID == "" || len(pack.Utterances) == 0 {
		return fmt.Errorf("empty campaign")
	}
	if pol.EmbedDim <= 0 || pol.InfoNCETau <= 0 || pol.InfoNCELr <= 0 || pol.InfoNCESteps <= 0 {
		return fmt.Errorf("bad embed policy")
	}
	if pol.SoftDTWGamma <= 0 || pol.GapCost < 0 || pol.RiskTarget < 0 || pol.RiskTarget > 1 {
		return fmt.Errorf("bad align/risk policy")
	}
	if len(pol.TempGrid) == 0 || len(pol.ThrGrid) == 0 {
		return fmt.Errorf("empty grids")
	}
	for _, u := range pack.Utterances {
		if u.UttID == "" || len(u.Hyp) == 0 || len(u.Ref) == 0 {
			return fmt.Errorf("bad utterance")
		}
		if u.Fold != "train" && u.Fold != "calib" && u.Fold != "eval" {
			return fmt.Errorf("bad fold")
		}
		if len(u.Kin) != len(u.Hyp) {
			return fmt.Errorf("kin length")
		}
		for _, k := range u.Kin {
			if k < 0 || k != k { // NaN check
				return fmt.Errorf("bad kin")
			}
		}
	}
	return nil
}
