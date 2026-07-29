package m8

import "environment/k3"

// Journal record kind strings (normative; see docs/pact_n4.md).
const (
	KindSample = "sample"
	KindFence  = "fence"
	KindRoster = "roster"
)

// Rec is one journal record.
type Rec struct {
	Kind  string            `json:"kind"`
	Pid   int               `json:"pid,omitempty"`
	Pages int               `json:"pages,omitempty"`
	Lane  string            `json:"lane,omitempty"`
	Gen   int               `json:"gen,omitempty"`
	Patch map[string]string `json:"patch,omitempty"`
}

// WeaveResult holds per-lane high-water values after journal reconstruct.
type WeaveResult struct {
	Peaks map[string]int
	Final *k3.Buf
	Gen   int
}
