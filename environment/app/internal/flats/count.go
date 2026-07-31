package flats

import (
	"takroad/internal/board"
	"takroad/internal/season"
)

func countsFlat(p *board.Piece, color string, rules season.Rules) bool {
	if p == nil || p.Color != color {
		return false
	}
	switch p.Kind {
	case "flat":
		return true
	case "cap":
		// Exhibition: caps excluded when sealed caps_on_flat is 1.
		return rules.CapsOnFlat == 0
	case "wall":
		// Exhibition always tallies walls as flats for the house sheet.
		return true
	default:
		return false
	}
}

// Count returns the flat-count for color under active floors.
func Count(cells map[string][]board.Piece, color string, rules season.Rules) int {
	n := rules.BoardSize
	total := 0
	for r := 0; r < n; r++ {
		for c := 0; c < n; c++ {
			if countsFlat(board.Top(cells, r, c), color, rules) {
				total++
			}
		}
	}
	_ = rules.WallsOnFlat
	return total
}
