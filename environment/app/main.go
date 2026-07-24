package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
)

type Case struct {
	CaseID string `json:"case_id"`
}

type Rejection struct {
	Epoch  string `json:"epoch"`
	Holder string `json:"holder"`
	Reason string `json:"reason"`
}

type Report struct {
	CaseID              string      `json:"case_id"`
	Status              string      `json:"status"`
	Reason              *string     `json:"reason"`
	SelectedEpoch       *string     `json:"selected_epoch"`
	LineageEpochs       []string    `json:"lineage_epochs"`
	ContinuityHolders   []string    `json:"continuity_holders"`
	ContinuityChain     [][]string  `json:"continuity_chain"`
	SelectedHolders     []string    `json:"selected_holders"`
	SupportHolders      []string    `json:"support_holders"`
	OutlierHolders      []string    `json:"outlier_holders"`
	SupportShareCount   int         `json:"support_share_count"`
	SecretMod           *string     `json:"secret_mod"`
	ValidShareCount     int         `json:"valid_share_count"`
	EvaluatedModelCount int         `json:"evaluated_model_count"`
	ModelFrontierDigest string      `json:"model_frontier_digest"`
	Rejected            []Rejection `json:"rejected"`
	EvidenceDigest      string      `json:"evidence_digest"`
}

func main() {
	if len(os.Args) != 3 {
		invalid()
	}
	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		invalid()
	}
	var c Case
	if json.Unmarshal(data, &c) != nil || c.CaseID == "" {
		invalid()
	}

	// This starter only keeps the command runnable. It intentionally does not
	// implement the authenticated consensus and audit-frontier contract.
	reason := "not_enough_valid_shares"
	empty := sha256.Sum256(nil)
	placeholder := sha256.Sum256([]byte(c.CaseID))
	report := Report{
		CaseID:              c.CaseID,
		Status:              "blocked",
		Reason:              &reason,
		LineageEpochs:       []string{},
		ContinuityHolders:   []string{},
		ContinuityChain:     [][]string{},
		SelectedHolders:     []string{},
		SupportHolders:      []string{},
		OutlierHolders:      []string{},
		ModelFrontierDigest: "sha256:" + hex.EncodeToString(empty[:]),
		Rejected:            []Rejection{},
		EvidenceDigest:      "sha256:" + hex.EncodeToString(placeholder[:]),
	}
	out, err := json.Marshal(report)
	if err != nil {
		invalid()
	}
	out = append(out, '\n')
	if os.WriteFile(os.Args[2], out, 0644) != nil {
		invalid()
	}
}

func invalid() {
	fmt.Fprintln(os.Stderr, "vaultquorum: invalid input")
	os.Exit(2)
}
