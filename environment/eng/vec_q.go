package eng

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"
)

// JoinBands builds the digest payload for band vectors keyed by sid.
func JoinBands(sids []string, bands map[string][]float64) string {
	sort.Strings(sids)
	parts := make([]string, 0, len(sids))
	for _, sid := range sids {
		b := bands[sid]
		cells := make([]string, len(b))
		for i, v := range b {
			cells[i] = fmt.Sprintf("%.6f", v)
		}
		parts = append(parts, strings.Join(cells, ","))
	}
	return strings.Join(parts, "|")
}

// HexDigest returns lowercase SHA-256 hex of s.
func HexDigest(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}
