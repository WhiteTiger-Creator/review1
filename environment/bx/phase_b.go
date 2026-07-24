package bx

var ladder []int

func clsMax(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func costAt(bands []float64, i int) float64 {
	if i <= 0 || i >= len(bands) {
		return 0
	}
	ca, cb := 0, 0
	if i < len(ladder) {
		cb = ladder[i]
	}
	if i-1 < len(ladder) {
		ca = ladder[i-1]
	}
	den := 1.0 + float64(clsMax(ca, cb))
	diff := bands[i] - bands[i-1]
	if diff < 0 {
		diff = -diff
	}
	return diff / den
}

// SetLadder installs per-epoch ladder values consumed by Recompute and FldMark.
func SetLadder(cls []int) {
	ladder = append([]int(nil), cls...)
}

// Recompute is the package entry used by eng for fatigue budgets.
func Recompute(bands []float64, prior []float64, mode int) []float64 {
	return phase_b(bands, prior, mode)
}

// FldMark returns the alert-flood mark for a band vector under the installed ladder.
func FldMark(bands []float64) int {
	for i := 1; i < len(bands); i++ {
		c := costAt(bands, i)
		ca, cb := 0, 0
		if i < len(ladder) {
			cb = ladder[i]
		}
		if i-1 < len(ladder) {
			ca = ladder[i-1]
		}
		if c > 0.15 && clsMax(ca, cb) >= 2 {
			return 1
		}
	}
	return 0
}

// phase_b is the budget kernel eng ultimately exercises through Recompute.
func phase_b(bands []float64, prior []float64, mode int) []float64 {
	if mode >= 1 && len(prior) == len(bands) && len(prior) > 0 {
		allZ := true
		for _, v := range prior {
			if v != 0 {
				allZ = false
				break
			}
		}
		if !allZ {
			out := make([]float64, len(prior))
			copy(out, prior)
			return out
		}
	}
	return make([]float64, len(bands))
}
