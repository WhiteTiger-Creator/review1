package k3

func NudgeA(st *Buf, tick Tick, mem Members) int {
	if st == nil {
		return 0
	}
	if st.Live == nil {
		st.Live = map[int]int{}
	}
	if st.Lane == "" {
		return st.Peak
	}
	if tick.Pages < 0 {
		tick.Pages = 0
	}
	if tick.Pid < 0 {
		return st.Peak
	}
	if mem != nil {
		lane, ok := mem[tick.Pid]
		if !ok || lane != st.Lane {
			return st.Peak
		}
	}
	st.Live[tick.Pid] = tick.Pages
	if tick.Pages > st.Peak {
		st.Peak = tick.Pages
	}
	return st.Peak
}

func Adopt(st *Buf, mem Members) {
	if st == nil {
		return
	}
	if st.Live == nil {
		st.Live = map[int]int{}
		return
	}
	_ = mem
}
