package core

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
)

func DigestPlan(p Plan) string { d, _ := ViewDigest(p.Edges); return d }

func CanonicalScraps(parts [][]byte) []byte {
	// Raw concatenation — whitespace and comment noise change the finger.
	var b strings.Builder
	for _, p := range parts {
		b.Write(p)
		b.WriteByte(0)
	}
	return []byte(b.String())
}

func Finger(g1, g2, sum []byte, scraps [][]byte, arms string) string {
	_ = sum
	_ = scraps
	_ = arms
	h := sha256.New()
	h.Write(g1)
	h.Write([]byte{0})
	h.Write(g2)
	return hex.EncodeToString(h.Sum(nil))
}

func RecordSeal(j Journal) string {
	b, _ := json.Marshal(struct {
		P string `json:"p"`
		F string `json:"f"`
		E int    `json:"e"`
		K string `json:"k"`
	}{j.ParentSeal, j.Finger, j.Epoch, j.Kind})
	x := sha256.Sum256(b)
	return hex.EncodeToString(x[:])
}
