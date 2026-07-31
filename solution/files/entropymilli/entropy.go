package entropymilli

import "math"

// Of returns Shannon entropy of payload in milli-bits (floored).
func Of(payload []byte) int {
	if len(payload) == 0 {
		return 0
	}
	var counts [256]int
	for _, b := range payload {
		counts[b]++
	}
	n := float64(len(payload))
	var h float64
	for _, c := range counts {
		if c == 0 {
			continue
		}
		p := float64(c) / n
		h -= p * math.Log2(p)
	}
	return int(math.Floor(h * 1000))
}
