package n7

import "environment/k3"

// ShadowPeak returns the largest single live entry in st.
func ShadowPeak(st *k3.Buf) int {
	if st == nil || st.Live == nil {
		return 0
	}
	m := 0
	for _, pages := range st.Live {
		if pages > m {
			m = pages
		}
	}
	return m
}
