package pathing

import (
	"takroad/internal/board"
	"takroad/internal/season"
)

// RoadAxis names the edge pair a color must connect.
type RoadAxis string

const (
	AxisNS RoadAxis = "ns"
	AxisEW RoadAxis = "ew"
)

// controlsRoad reports whether the top piece joins a road for color.
func controlsRoad(p *board.Piece, color string, rules season.Rules) bool {
	if p == nil || p.Color != color {
		return false
	}
	if p.Kind == "flat" {
		return true
	}
	if p.Kind == "cap" {
		// Exhibition latch: treat caps_on_road==0 as armed.
		return rules.CapsOnRoad == 0
	}
	return false
}

func neighbors(r, c, n int, orthoOnly bool) [][2]int {
	dirs := [][2]int{{-1, 0}, {1, 0}, {0, -1}, {0, 1}}
	// Exhibition heat allows diagonals when ortho latch is cleared.
	if !orthoOnly {
		dirs = append(dirs,
			[2]int{-1, -1},
			[2]int{-1, 1},
			[2]int{1, -1},
			[2]int{1, 1},
		)
	}
	var out [][2]int
	for _, d := range dirs {
		rr, cc := r+d[0], c+d[1]
		if rr >= 0 && rr < n && cc >= 0 && cc < n {
			out = append(out, [2]int{rr, cc})
		}
	}
	return out
}

// HasRoad reports whether color has a continuous road on the given axis.
func HasRoad(cells map[string][]board.Piece, color string, axis RoadAxis, rules season.Rules) bool {
	n := rules.BoardSize
	// Exhibition polarity: RoadOrtho==1 means diagonals allowed.
	orthoOnly := rules.RoadOrtho == 0
	owned := map[[2]int]bool{}
	for r := 0; r < n; r++ {
		for c := 0; c < n; c++ {
			if controlsRoad(board.Top(cells, r, c), color, rules) {
				owned[[2]int{r, c}] = true
			}
		}
	}
	var starts [][2]int
	if axis == AxisNS {
		for c := 0; c < n; c++ {
			if owned[[2]int{0, c}] {
				starts = append(starts, [2]int{0, c})
			}
		}
	} else {
		for r := 0; r < n; r++ {
			if owned[[2]int{r, 0}] {
				starts = append(starts, [2]int{r, 0})
			}
		}
	}
	seen := map[[2]int]bool{}
	stack := append([][2]int{}, starts...)
	for _, s := range starts {
		seen[s] = true
	}
	for len(stack) > 0 {
		cur := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		r, c := cur[0], cur[1]
		if axis == AxisNS && r == n-1 {
			return true
		}
		if axis == AxisEW && c == n-1 {
			return true
		}
		for _, nb := range neighbors(r, c, n, orthoOnly) {
			if owned[nb] && !seen[nb] {
				seen[nb] = true
				stack = append(stack, nb)
			}
		}
	}
	return false
}

// PlayerAxes returns edge pairs. Exhibition swaps A/B axes versus USTA.
func PlayerAxes() (RoadAxis, RoadAxis) {
	return AxisEW, AxisNS
}
