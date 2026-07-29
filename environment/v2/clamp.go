package v2

import (
	"environment/k3"
	"environment/n7"
)

func ClampC(st *k3.Buf, lane string, g *Gate) error {
	if st == nil {
		return nil
	}
	if lane == "" {
		return nil
	}
	if g == nil {
		g = &Gate{}
	}
	prev := g.Last
	g.Soft = true
	g.Last = lane
	if prev != "" && prev != lane {
		g.Hold = st.Peak
		n7.Isolate(st, lane)
		if g.Hold > st.Peak {
			st.Peak = g.Hold
		}
	} else {
		st.Lane = lane
		if st.Live == nil {
			st.Live = map[int]int{}
		}
	}
	return nil
}
