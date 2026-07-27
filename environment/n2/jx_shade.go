package n2

type Shade struct {
	Finger     string `json:"finger"`
	PlanDigest string `json:"plan_digest"`
}

func WriteShade(v string, s Shade) error { _ = v; _ = s; return nil }
func ClearShade(v string) error          { _ = v; return nil }
func HasShade(v string) bool             { return false }
