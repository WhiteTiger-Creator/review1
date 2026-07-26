package core

type Entry struct {
	ModulePath string `json:"module_path"`
	Version    string `json:"version"`
	Sum        string `json:"sum"`
}
type Tile struct {
	Gen     int     `json:"gen"`
	Note    string  `json:"note"`
	Entries []Entry `json:"entries"`
}
type Need struct {
	ModulePath string `json:"module_path"`
	Version    string `json:"version"`
}
type Change struct {
	From      string `json:"from"`
	To        string `json:"to"`
	ToVersion string `json:"to_version"`
}
type Source struct {
	Entry      Entry
	Provenance map[string]bool
}
type State struct {
	Rows    map[string]Source
	Needs   map[string]Need
	Changes map[string]Change
}
type Edge struct {
	ModulePath string `json:"module_path"`
	Version    string `json:"version"`
	ReplaceTo  string `json:"replace_to"`
	Cls        string `json:"cls"`
	Sum        string `json:"sum"`
}
type Plan struct {
	Edges []Edge `json:"edges"`
}
type Journal struct {
	Seq        int    `json:"seq"`
	ParentSeal string `json:"parent_seal"`
	Finger     string `json:"finger"`
	Plan       Plan   `json:"plan"`
	Soft       bool   `json:"soft"`
	Epoch      int    `json:"epoch"`
	NestSeal   string `json:"nest_seal"`
	PlanDigest string `json:"plan_digest"`
	Kind       string `json:"kind"`
}
type Snapshot struct {
	Journal Journal `json:"journal"`
	Seal    string  `json:"seal"`
}
