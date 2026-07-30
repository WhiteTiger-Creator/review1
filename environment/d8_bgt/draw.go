package d8_bgt

import "wavellite_dc/q4"

func FitDraw(in []q4.Unit, ceiling int) ([]q4.Unit, int) {
	out := make([]q4.Unit, 0, len(in))
	out = append(out, in...)
	return out, 0
}
