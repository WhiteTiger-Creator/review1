package scep

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
)

type CA struct {
	SubjectCommonName string
	signerKey         []byte

	mu         sync.Mutex
	nextSerial int64
}

func NewCA() *CA {
	return &CA{
		SubjectCommonName: "Example SCEP Intermediate CA",
		signerKey:         []byte("enrollward-ca-signer-key-2026"),
		nextSerial:        4096,
	}
}

func (c *CA) issueSerial() int64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	s := c.nextSerial
	c.nextSerial++
	return s
}

// SignerFingerprint returns the authority's keyed fingerprint over the identity
// fields of a certificate this CA issued. A caller cannot reproduce it without
// the authority's signer key, so a matching fingerprint is what proves a renewal
// signer was genuinely issued by this CA rather than merely carrying its name.
func (c *CA) SignerFingerprint(s *SignerCertificate) string {
	canonical := fmt.Sprintf("%s\n%s\n%d", s.SubjectCommonName, s.IssuerCommonName, s.NotAfterDays)
	mac := hmac.New(sha256.New, c.signerKey)
	mac.Write([]byte(canonical))
	return hex.EncodeToString(mac.Sum(nil))
}
