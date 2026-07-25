package w3

import (
	"encoding/json"
	"fmt"
	"hxenv/lib/core"
	"hxenv/n2"
	"hxenv/p6"
	"os"
)

func Check(v, nest, out string) (string, error) {
	if n2.HasShade(v) {
		return "pending", nil
	}
	s, ok, e := n2.Replay(v)
	if e != nil || !ok || s.Journal.Soft {
		return "pending", e
	}
	snap, sok, e := n2.LoadSnap(v)
	if e != nil || !sok || snap.Seal != s.Seal || snap.Journal.Finger != s.Journal.Finger {
		return "pending", e
	}
	seal, e := p6.Seal(nest)
	if e != nil || seal != s.Journal.NestSeal {
		return "pending", e
	}
	b, e := os.ReadFile(out)
	if e != nil {
		return "pending", nil
	}
	var q struct {
		ViewDigest string `json:"view_digest"`
	}
	if json.Unmarshal(b, &q) != nil {
		return "pending", nil
	}
	d, _ := core.ViewDigest(s.Journal.Plan.Edges)
	if d != q.ViewDigest {
		return "pending", nil
	}
	return "settled", nil
}

func Status(v, n, o string) error {
	s, e := Check(v, n, o)
	if e != nil {
		return e
	}
	return json.NewEncoder(stdout{}).Encode(map[string]string{"state": s})
}

type stdout struct{}

func (stdout) Write(b []byte) (int, error) { return fmt.Print(string(b)) }
