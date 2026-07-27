package knot

import "errors"

var errNilBook = errors.New("nil book")

type Book struct {
	W      map[string]float64
	Sig    map[string]float64
	Prior  map[string]float64
	Alpha  float64
	Cuts   []float64
	Frozen bool
	Shadow map[string]float64
}

func Key(sid, iid string) string {
	return sid + "/" + iid
}

func BandOf(w float64, cuts []float64) int {
	n := 0
	for _, c := range cuts {
		if w > c {
			n++
		}
	}
	return n
}
