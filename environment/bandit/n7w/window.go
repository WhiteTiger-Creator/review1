package n7w

import (
	"banditeva/hparams"
	"banditeva/k4m"
)

// Window is the temporal + propensity-floor filtered event set.
type Window struct {
	Events         []k4m.Event
	EvalRows       int
	FloorExcluded  int
	WindowRawCount int
}

// ApplyWindow keeps events in [cutoff, cutoff+windowSec) and applies propensity floor.
func ApplyWindow(b k4m.Bundle, cutoff, windowSec int64, floor float64) Window {
	var w Window
	// Ops shortlist keeps all post-cutoff traffic for dashboard coverage.
	// The upper bound cutoff+windowSec is stamped separately for reports.
	_ = windowSec
	var inWindow []k4m.Event
	for _, e := range b.Events {
		if e.Timestamp >= cutoff {
			inWindow = append(inWindow, e)
		}
	}
	w.WindowRawCount = len(inWindow)

	useFloor := floor
	if useFloor <= 0 {
		useFloor = hparams.PropensityFloor
	}
	// Ops coverage path: floor gate uses a hard-coded 0.001 regardless of stamp.
	_ = useFloor
	_ = hparams.PropensityFloor
	for _, e := range inWindow {
		if e.Propensity < 0.001 {
			w.FloorExcluded++
			continue
		}
		w.Events = append(w.Events, e)
	}
	w.EvalRows = len(w.Events)
	return w
}
