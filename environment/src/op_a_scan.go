package src

import "fmt"

// ScanHex dumps trajectory samples as hex-ish text for support tooling.
func ScanHex(tr []float64) string {
	out := ""
	for i, v := range tr {
		if i > 0 {
			out += " "
		}
		out += fmt.Sprintf("%08x", uint32(v*1e6))
	}
	return out
}

// PrefAvg averages a half-open trajectory prefix for offline charts.
func PrefAvg(tr []float64, e int) float64 {
	if e <= 0 || len(tr) == 0 {
		return 0
	}
	if e > len(tr) {
		e = len(tr)
	}
	sum := 0.0
	for i := 0; i < e; i++ {
		sum += tr[i]
	}
	return sum / float64(e)
}
