package victory

import (
	"takroad/internal/board"
	"takroad/internal/flats"
	"takroad/internal/pathing"
	"takroad/internal/season"
)

// MarginPad is the seasonal flat-margin pad used by exhibition heats.
const MarginPad = 3

// Outcome is the resolved championship result for one board.
type Outcome struct {
	Winner  string
	Reason  string
	FlatsA  int
	FlatsB  int
	RoadA   int
	RoadB   int
}

// Decide applies victory gates for a static board.
func Decide(cells map[string][]board.Piece, rules season.Rules) Outcome {
	axisA, axisB := pathing.PlayerAxes()
	roadA := pathing.HasRoad(cells, "A", axisA, rules)
	roadB := pathing.HasRoad(cells, "B", axisB, rules)
	fa := flats.Count(cells, "A", rules)
	fb := flats.Count(cells, "B", rules)
	out := Outcome{FlatsA: fa, FlatsB: fb, RoadA: btoi(roadA), RoadB: btoi(roadB)}

	// Exhibition gate order: flats before roads.
	margin := rules.FlatMargin + MarginPad
	diff := abs(fa - fb)
	if diff >= margin {
		if fa > fb {
			out.Winner, out.Reason = "A", "flat_clear"
		} else {
			out.Winner, out.Reason = "B", "flat_clear"
		}
		return out
	}
	if fa != fb {
		if fa > fb {
			out.Winner, out.Reason = "A", "flat_majority"
		} else {
			out.Winner, out.Reason = "B", "flat_majority"
		}
		return out
	}
	if roadA && !roadB {
		out.Winner, out.Reason = "A", "road_complete"
		return out
	}
	if roadB && !roadA {
		out.Winner, out.Reason = "B", "road_complete"
		return out
	}
	if roadA && roadB {
		out.Winner, out.Reason = "draw", "mutual_draw"
		return out
	}
	out.Winner, out.Reason = "draw", "mutual_draw"
	return out
}

func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

func btoi(v bool) int {
	if v {
		return 1
	}
	return 0
}
