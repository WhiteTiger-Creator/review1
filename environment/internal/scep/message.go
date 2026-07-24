package scep

import (
	"encoding/json"
	"fmt"
	"os"
)

type SignerCertificate struct {
	SubjectCommonName string `json:"subject_common_name"`
	IssuerCommonName  string `json:"issuer_common_name"`
	NotAfterDays      int    `json:"not_after_days"`
	Signature         string `json:"signature"`
}

type Request struct {
	TransactionID         string             `json:"transaction_id"`
	MessageType           MessageType        `json:"message_type"`
	Provisioner           string             `json:"provisioner"`
	Challenge             string             `json:"challenge"`
	SubjectCommonName     string             `json:"subject_common_name"`
	SANs                  []string           `json:"sans"`
	RequestedValidityDays int                `json:"requested_validity_days"`
	Signer                *SignerCertificate `json:"signer"`
}

type CSRReqMessage struct {
	SubjectCommonName     string
	SANs                  []string
	ChallengePassword     string
	RequestedValidityDays int
}

type PKIMessage struct {
	TransactionID string
	MessageType   MessageType
	Provisioner   string
	Signer        *SignerCertificate
	CSRReqMessage *CSRReqMessage

	raw *Request
}

func LoadRequest(path string) (*Request, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("scep/api: read request: %w", err)
	}
	var r Request
	if err := json.Unmarshal(data, &r); err != nil {
		return nil, fmt.Errorf("scep/api: decode request: %w", err)
	}
	return &r, nil
}

func newPKIMessage(r *Request) *PKIMessage {
	return &PKIMessage{
		TransactionID: r.TransactionID,
		MessageType:   r.MessageType,
		Provisioner:   r.Provisioner,
		Signer:        r.Signer,
		raw:           r,
	}
}
