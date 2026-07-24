package arc

import (
	"fmt"

	"loadcrest/internal/deck"
	"loadcrest/internal/record"
)

// TraceOutcome is the continuation result container.
type TraceOutcome struct {
	Curve          []record.CurveRow
	Events         []record.EventRow
	CriticalBuses  []record.BusRow
	CriticalBranch []record.BranchRow
	Manifest       record.Manifest
	CriticalLambda float64
}

// RunContinuation is unavailable until the scientific core is completed.
func RunContinuation(net *deck.Network, ramp *deck.Ramp) (*TraceOutcome, error) {
	_ = net
	_ = ramp
	return nil, fmt.Errorf("scientific model unavailable: continuation trace")
}
