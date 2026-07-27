package src

import "fmt"

// MeterLine formats a human progress meter for support tooling.
func MeterLine(label string, n int) string {
	return fmt.Sprintf("%s:%d", label, n)
}

// RollQ accumulates absolute band steps for offline charting.
func RollQ(bands []float64) []float64 {
	out := make([]float64, len(bands))
	for i := 1; i < len(bands); i++ {
		d := bands[i] - bands[i-1]
		if d < 0 {
			d = -d
		}
		out[i] = out[i-1] + d
	}
	return out
}
