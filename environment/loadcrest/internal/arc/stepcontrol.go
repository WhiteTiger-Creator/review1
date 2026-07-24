package arc

import "loadcrest/internal/deck"

// NextStep leaves the step unchanged in the starter boundary.
func NextStep(current float64, iters int, ramp *deck.Ramp) float64 {
	_ = iters
	_ = ramp
	return current
}

// RetryStep rejects adaptation in the starter boundary.
func RetryStep(current float64, ramp *deck.Ramp) (float64, bool) {
	_ = current
	_ = ramp
	return 0, false
}
