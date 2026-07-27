package core

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strings"
)

func DigestPlan(p Plan) string { d, _ := ViewDigest(p.Edges); return d }

func CanonicalScraps(parts [][]byte) []byte {
	var req, flow []string
	for _, b := range parts {
		for _, raw := range strings.Split(string(b), "\n") {
			s := strings.TrimSpace(raw)
			if i := strings.Index(s, "//"); i >= 0 {
				s = strings.TrimSpace(s[:i])
			}
			if i := strings.Index(s, "#"); i >= 0 {
				s = strings.TrimSpace(s[:i])
			}
			if s == "" || s == "require (" || s == ")" {
				continue
			}
			f := strings.Fields(s)
			if len(f) == 0 {
				continue
			}
			if f[0] == "module" || f[0] == "go" {
				continue
			}
			if f[0] == "replace" || f[0] == "dropreplace" {
				flow = append(flow, strings.Join(f, " "))
				continue
			}
			if f[0] == "require" {
				f = f[1:]
			}
			if len(f) >= 2 && strings.Contains(f[0], ".") {
				req = append(req, f[0]+" "+f[1])
			}
		}
	}
	sort.Strings(req)
	return []byte(strings.Join(append(req, flow...), "\n"))
}

func Finger(g1, g2, sum []byte, scraps [][]byte, arms string) string {
	h := sha256.New()
	h.Write(g1)
	h.Write([]byte{0})
	h.Write(g2)
	h.Write([]byte{0})
	h.Write(sum)
	h.Write([]byte{0})
	h.Write(CanonicalScraps(scraps))
	h.Write([]byte{0})
	parts := strings.Fields(strings.ReplaceAll(arms, ",", " "))
	sort.Strings(parts)
	h.Write([]byte(strings.Join(parts, ",")))
	return hex.EncodeToString(h.Sum(nil))
}

func RecordSeal(j Journal) string {
	b, _ := json.Marshal(struct {
		P string `json:"p"`
		F string `json:"f"`
		E int    `json:"e"`
		K string `json:"k"`
		N string `json:"n"`
		D string `json:"d"`
	}{j.ParentSeal, j.Finger, j.Epoch, j.Kind, j.NestSeal, j.PlanDigest})
	x := sha256.Sum256(b)
	return hex.EncodeToString(x[:])
}
