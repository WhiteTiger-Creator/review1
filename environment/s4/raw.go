package s4

// RawTally accumulates non-negative sample page counts.
func RawTally(samples []int) int {
	n := 0
	for _, p := range samples {
		if p > 0 {
			n += p
		}
	}
	return n
}
