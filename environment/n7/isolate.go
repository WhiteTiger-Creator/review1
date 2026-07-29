package n7

import "environment/k3"

// Isolate prepares st for a new lane window after a fence or reload handoff.
func Isolate(st *k3.Buf, nextLane string) {
	if st == nil {
		return
	}
	if st.Live == nil {
		st.Live = map[int]int{}
	} else {
		for pid := range st.Live {
			delete(st.Live, pid)
		}
	}
	if nextLane != "" {
		st.Lane = nextLane
	}
}
