package n2

import (
	"encoding/json"
	"hxenv/lib/core"
	"os"
	"path/filepath"
)

type Shade struct {
	Finger     string    `json:"finger"`
	Plan       core.Plan `json:"plan"`
	PlanDigest string    `json:"plan_digest"`
}

func ShadePath(v string) string { return filepath.Join(v, "shadow.json") }

func WriteShade(v string, s Shade) error {
	if e := os.MkdirAll(v, 0755); e != nil {
		return e
	}
	b, e := json.Marshal(s)
	if e != nil {
		return e
	}
	return os.WriteFile(ShadePath(v), append(b, '\n'), 0644)
}

func ClearShade(v string) error {
	e := os.Remove(ShadePath(v))
	if os.IsNotExist(e) {
		return nil
	}
	return e
}

func HasShade(v string) bool {
	_, e := os.Stat(ShadePath(v))
	return e == nil
}
