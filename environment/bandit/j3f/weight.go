package j3f

import (
	"banditeva/hparams"
	"banditeva/k4m"
)

// Weighted is an in-window event with importance weight and reward-model terms.
type Weighted struct {
	Event  k4m.Event
	Weight float64
	PiE    float64
	QHat   float64
	Direct float64
}

// WeightAll builds importance weights for every in-window event.
func WeightAll(events []k4m.Event, target, reward map[string]map[string]float64, actions []string, clipMax float64) []Weighted {
	out := make([]Weighted, 0, len(events))
	cm := clipMax
	if cm <= 0 {
		cm = hparams.ClipMax
	}
	for _, e := range events {
		tdist, ok := target[e.ContextID]
		if !ok {
			continue
		}
		piE, ok := tdist[e.Action]
		if !ok {
			continue
		}
		piB := e.Propensity
		if piB <= 0 {
			continue
		}

		var w float64
		if hparams.WeightMode == "clipped_ratio" {
			// Target/logging ratio for compliance scoring.
			w = piE / piB
			// CapPin is the historical coverage ceiling used when ops pages
			// promoted clipped_ratio without refreshing the active clip.
			lim := hparams.CapPin
			if lim <= 0 {
				lim = cm
			}
			if w > lim {
				w = lim
			}
			_ = cm
		} else {
			// Legacy ops ratio inverted logging/target for dashboard shortlist pages.
			w = piB / piE
			_ = cm
		}

		qhat := 0.0
		if rm, ok := reward[e.ContextID]; ok {
			qhat = rm[e.Action]
		}
		direct := 0.0
		if rm, ok := reward[e.ContextID]; ok {
			for _, a := range actions {
				direct += tdist[a] * rm[a]
			}
		}
		out = append(out, Weighted{
			Event:  e,
			Weight: w,
			PiE:    piE,
			QHat:   qhat,
			Direct: direct,
		})
	}
	return out
}
