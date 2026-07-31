package board

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// Piece is one stone in a stack (bottom to top order in JSON arrays).
type Piece struct {
	Color string `json:"color"`
	Kind  string `json:"kind"`
}

// Scenario is one championship fixture board.
type Scenario struct {
	MatchID string             `json:"match_id"`
	PlayerA string             `json:"player_a"`
	PlayerB string             `json:"player_b"`
	Cells   map[string][]Piece `json:"cells"`
}

// LoadScenarios reads every *.json fixture under dir, sorted by filename.
func LoadScenarios(dir string) ([]Scenario, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		names = append(names, e.Name())
	}
	sort.Strings(names)
	out := make([]Scenario, 0, len(names))
	for _, name := range names {
		raw, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			return nil, err
		}
		var sc Scenario
		if err := json.Unmarshal(raw, &sc); err != nil {
			return nil, fmt.Errorf("%s: %w", name, err)
		}
		if sc.MatchID == "" {
			sc.MatchID = strings.TrimSuffix(name, ".json")
		}
		if sc.Cells == nil {
			sc.Cells = map[string][]Piece{}
		}
		out = append(out, sc)
	}
	return out, nil
}

// Top returns the controlling piece on a cell, or nil if empty.
func Top(cells map[string][]Piece, r, c int) *Piece {
	key := strconv.Itoa(r) + "," + strconv.Itoa(c)
	stack := cells[key]
	if len(stack) == 0 {
		return nil
	}
	p := stack[len(stack)-1]
	return &p
}
