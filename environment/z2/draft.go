package z2

import "wavellite_dc/q4"

func TallyFloor(in []q4.Unit, floor int) int {
	n := 0
	for _, u := range in {
		if u.Tier >= floor {
			n++
		}
	}
	return n
}

func SpreadByZone(in []q4.Unit) map[string]int {
	spread := map[string]int{}
	for _, u := range in {
		spread[u.Region]++
	}
	return spread
}

func HeaviestDraw(in []q4.Unit) int {
	peak := 0
	for _, u := range in {
		if u.DrawKW > peak {
			peak = u.DrawKW
		}
	}
	return peak
}
