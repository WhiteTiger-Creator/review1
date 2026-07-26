package emit

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	"core.net/fx/internal/state"
	"core.net/fx/x3"
)

// Row is one scenario emission.
type Row struct {
	Outcome      string `json:"outcome"`
	MatrixDigest string `json:"matrix_digest"`
}

// BuildRow composes the authorized trust outcome and digest for one scenario.
func BuildRow(s *state.Bundle, id, tok, live string) Row {
	s.ScenarioID = id
	stamp := s.StampFor(id)
	epoch := s.EpochFor(id)
	pol := x3.Apply(s, stamp, epoch)
	outcome := decide(tok, live, pol)
	return Row{
		Outcome:      outcome,
		MatrixDigest: MatrixDigest(id, outcome),
	}
}

func decide(tok, live, pol string) string {
	if tok == "" {
		return "deny"
	}
	if live == "x0" {
		return "deny"
	}
	if pol == "neg" {
		return "deny"
	}
	if live == "x1" || live == "x2" {
		if pol == "pos" {
			return "allow"
		}
	}
	return "deny"
}

// MatrixDigest follows docs/digest_canon.md.
func MatrixDigest(scenarioID, outcome string) string {
	payload := fmt.Sprintf("%s|%s", scenarioID, outcome)
	sum := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(sum[:])[:16]
}
