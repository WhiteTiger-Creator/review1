package x6_sig

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	"wavellite_dc/q4"
)

func BindMark(row q4.SiteRow) string {
	text := fmt.Sprintf("%s:%d:%d", row.Name, row.ReadinessIndex, row.CertifiedCount)
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}
