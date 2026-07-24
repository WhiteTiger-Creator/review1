package grid

import "loadcrest/internal/deck"

// TerminalFlow holds terminal powers.
type TerminalFlow struct {
	BranchID string
	Status   string
	From     string
	To       string
	PFrom    float64
	QFrom    float64
	PTo      float64
	QTo      float64
	PLoss    float64
	QLoss    float64
}

// ComputeFlows returns zero flows in the starter boundary.
func ComputeFlows(buses []Bus, branches []Branch) []TerminalFlow {
	_ = buses
	out := make([]TerminalFlow, len(branches))
	for i, br := range branches {
		out[i] = TerminalFlow{BranchID: br.ID, Status: string(br.Status), From: br.From, To: br.To}
		_ = deck.BranchIN
	}
	return out
}
