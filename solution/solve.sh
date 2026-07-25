#!/bin/bash
set -euo pipefail

cat > /app/main.go <<'GO'
package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
)

type Coord struct{ Q, R int }

type Rules struct {
	Radius                int    `json:"radius"`
	MaxGroup              int    `json:"max_group"`
	TargetEjections       int    `json:"target_ejections"`
	RepetitionLimit       int    `json:"repetition_limit"`
	RepetitionEquivalence string `json:"repetition_equivalence"`
	KoWindow              int    `json:"ko_window"`
	NoProgressLimit       int    `json:"no_progress_limit"`
	MoveLimit             int    `json:"move_limit"`
	ContinuationDepth     int    `json:"continuation_depth"`
	QuiescenceDepth       int    `json:"quiescence_depth"`
	TempoCooldown         int    `json:"tempo_cooldown"`
	MomentumCap           int    `json:"momentum_cap"`
}

type Marble struct {
	Q      int    `json:"q"`
	R      int    `json:"r"`
	Player string `json:"player"`
}

type Cooldown struct {
	Q         int    `json:"q"`
	R         int    `json:"r"`
	Player    string `json:"player"`
	Remaining int    `json:"remaining"`
}

type Initial struct {
	NextPlayer string         `json:"next_player"`
	Ejections map[string]int `json:"ejections"`
	Momentum   map[string]int `json:"momentum"`
	Cooldowns  []Cooldown     `json:"cooldowns"`
	Marbles    []Marble       `json:"marbles"`
}

type Move struct {
	ID        string  `json:"id"`
	Player    string  `json:"player"`
	Marbles   [][]int `json:"marbles"`
	Direction string  `json:"direction"`
}

type Input struct {
	Players []string `json:"players"`
	Rules   Rules    `json:"rules"`
	Initial Initial  `json:"initial"`
	Moves   []Move   `json:"moves"`
}

type Result struct {
	ID          string  `json:"id"`
	Accepted    bool    `json:"accepted"`
	Reason      *string `json:"reason"`
	MoveType    *string `json:"move_type"`
	Pushed      int     `json:"pushed"`
	Ejected     int     `json:"ejected"`
	Momentum    map[string]int `json:"momentum"`
	NextPlayer  *string `json:"next_player"`
	PositionKey string  `json:"position_key"`
	LegalActionCount int `json:"legal_action_count"`
	LegalActionDigest string `json:"legal_action_digest"`
}

type Final struct {
	Status      string         `json:"status"`
	Winner      *string        `json:"winner"`
	LegalMoves  int            `json:"legal_moves"`
	NoProgress int            `json:"no_progress"`
	Ejections  map[string]int `json:"ejections"`
	Momentum   map[string]int `json:"momentum"`
	Cooldowns  []Cooldown     `json:"cooldowns"`
	NextPlayer *string        `json:"next_player"`
	PositionKey string         `json:"position_key"`
	Board       []Marble       `json:"board"`
}

type Report struct {
	Results      []Result     `json:"results"`
	Final        Final        `json:"final"`
	Continuation Continuation `json:"continuation"`
}

type LeafCounts struct {
	WinPlayer0      int `json:"win_player0"`
	WinPlayer1      int `json:"win_player1"`
	DrawRepetition  int `json:"draw_repetition"`
	DrawNoProgress  int `json:"draw_no_progress"`
	DrawMoveLimit   int `json:"draw_move_limit"`
	Horizon         int `json:"horizon"`
	Stalled         int `json:"stalled"`
}

type Continuation struct {
	Depth              int            `json:"depth"`
	QuiescenceDepth    int            `json:"quiescence_depth"`
	RootActionCount    int            `json:"root_action_count"`
	RootAnalyses       []RootAnalysis `json:"root_analyses"`
	Nodes              int            `json:"nodes"`
	QuiescenceNodes    int            `json:"quiescence_nodes"`
	Leaves             int            `json:"leaves"`
	LeafCounts         LeafCounts     `json:"leaf_counts"`
	Value              int            `json:"value"`
	Utility            Utility        `json:"utility"`
	OptimalActions     []string       `json:"optimal_actions"`
	PrincipalVariation []string `json:"principal_variation"`
	Digest             string   `json:"digest"`
}

type Utility struct {
	Outcome  int `json:"outcome"`
	Margin   int `json:"margin"`
	Momentum int `json:"momentum"`
	Tempo    int `json:"tempo"`
}

type RootAnalysis struct {
	Action             string     `json:"action"`
	Nodes              int        `json:"nodes"`
	QuiescenceNodes    int        `json:"quiescence_nodes"`
	Leaves             int        `json:"leaves"`
	LeafCounts         LeafCounts `json:"leaf_counts"`
	Utility            Utility    `json:"utility"`
	PrincipalVariation []string   `json:"principal_variation"`
	Digest             string     `json:"digest"`
}

type CooldownMark struct {
	Player    string
	Remaining int
}

type Action struct {
	Key      string
	State    *Engine
	Tactical bool
}

type Proof struct {
	Nodes          int
	QuiescenceNodes int
	Leaves         int
	LeafCounts     LeafCounts
	Value          int
	Utility        Utility
	OptimalActions []string
	PrincipalVariation []string
	RootAnalyses    []RootAnalysis
	Digest         string
}

var vectors = map[string]Coord{
	"E": {1, 0}, "NE": {1, -1}, "NW": {0, -1},
	"W": {-1, 0}, "SW": {-1, 1}, "SE": {0, 1},
}

var directionNames = []string{"E", "NE", "NW", "SE", "SW", "W"}

type Engine struct {
	in          Input
	board       map[Coord]string
	cooldowns   map[Coord]CooldownMark
	scores      map[string]int
	momentum    map[string]int
	next        string
	legal       int
	noProgress int
	status      string
	winner      *string
	repetitions map[string]int
	history     []string
}

func add(a, b Coord) Coord { return Coord{a.Q + b.Q, a.R + b.R} }

func abs(x int) int {
	if x < 0 { return -x }
	return x
}

func max3(a, b, c int) int {
	if b > a { a = b }
	if c > a { a = c }
	return a
}

func (e *Engine) onBoard(c Coord) bool {
	return max3(abs(c.Q), abs(c.R), abs(c.Q+c.R)) <= e.in.Rules.Radius
}

func (e *Engine) other(player string) string {
	if player == e.in.Players[0] { return e.in.Players[1] }
	return e.in.Players[0]
}

func sortedCoords(board map[Coord]string) []Coord {
	coords := make([]Coord, 0, len(board))
	for c := range board { coords = append(coords, c) }
	sort.Slice(coords, func(i, j int) bool {
		if coords[i].Q != coords[j].Q { return coords[i].Q < coords[j].Q }
		return coords[i].R < coords[j].R
	})
	return coords
}

func (e *Engine) boardList() []Marble {
	out := make([]Marble, 0, len(e.board))
	for _, c := range sortedCoords(e.board) {
		out = append(out, Marble{Q: c.Q, R: c.R, Player: e.board[c]})
	}
	return out
}

func sortedCooldownCoords(cooldowns map[Coord]CooldownMark) []Coord {
	coords := make([]Coord, 0, len(cooldowns))
	for c := range cooldowns { coords = append(coords, c) }
	sort.Slice(coords, func(i, j int) bool {
		if coords[i].Q != coords[j].Q { return coords[i].Q < coords[j].Q }
		return coords[i].R < coords[j].R
	})
	return coords
}

func (e *Engine) cooldownList() []Cooldown {
	out := make([]Cooldown, 0, len(e.cooldowns))
	for _, c := range sortedCooldownCoords(e.cooldowns) {
		mark := e.cooldowns[c]
		out = append(out, Cooldown{Q: c.Q, R: c.R, Player: mark.Player, Remaining: mark.Remaining})
	}
	return out
}

func cloneInts(values map[string]int) map[string]int {
	out := make(map[string]int, len(values))
	for key, value := range values { out[key] = value }
	return out
}

func (e *Engine) serializePosition(next string, board map[Coord]string, cooldowns map[Coord]CooldownMark) string {
	var b strings.Builder
	b.WriteString("next=")
	b.WriteString(next)
	b.WriteString("|score=")
	fmt.Fprintf(
		&b, "%s:%d,%s:%d|momentum=%s:%d,%s:%d|cooldown=",
		e.in.Players[0], e.scores[e.in.Players[0]],
		e.in.Players[1], e.scores[e.in.Players[1]],
		e.in.Players[0], e.momentum[e.in.Players[0]],
		e.in.Players[1], e.momentum[e.in.Players[1]],
	)
	for i, c := range sortedCooldownCoords(cooldowns) {
		if i > 0 { b.WriteByte(';') }
		mark := cooldowns[c]
		fmt.Fprintf(&b, "%d,%d:%s:%d", c.Q, c.R, mark.Player, mark.Remaining)
	}
	b.WriteString("|board=")
	for i, c := range sortedCoords(board) {
		if i > 0 { b.WriteByte(';') }
		fmt.Fprintf(&b, "%d,%d:%s", c.Q, c.R, board[c])
	}
	return b.String()
}

func (e *Engine) positionKey(next string) string {
	return e.serializePosition(next, e.board, e.cooldowns)
}

func rotate(c Coord) Coord { return Coord{-c.R, c.Q + c.R} }

func (e *Engine) equivalenceKey(next string) string {
	variants := 1
	reflections := 1
	if e.in.Rules.RepetitionEquivalence == "rotations" { variants = 6 }
	if e.in.Rules.RepetitionEquivalence == "dihedral" { variants, reflections = 6, 2 }
	best := ""
	for reflected := 0; reflected < reflections; reflected++ {
		transformed := make(map[Coord]string, len(e.board))
		transformedCooldowns := make(map[Coord]CooldownMark, len(e.cooldowns))
		for c, player := range e.board {
			if reflected == 1 { c = Coord{c.R, c.Q} }
			transformed[c] = player
		}
		for c, mark := range e.cooldowns {
			if reflected == 1 { c = Coord{c.R, c.Q} }
			transformedCooldowns[c] = mark
		}
		for turn := 0; turn < variants; turn++ {
			candidate := e.serializePosition(next, transformed, transformedCooldowns)
			if best == "" || candidate < best { best = candidate }
			rotated := make(map[Coord]string, len(transformed))
			for c, player := range transformed { rotated[rotate(c)] = player }
			transformed = rotated
			rotatedCooldowns := make(map[Coord]CooldownMark, len(transformedCooldowns))
			for c, mark := range transformedCooldowns { rotatedCooldowns[rotate(c)] = mark }
			transformedCooldowns = rotatedCooldowns
		}
	}
	return best
}

func cloneBoard(board map[Coord]string) map[Coord]string {
	out := make(map[Coord]string, len(board))
	for c, player := range board { out[c] = player }
	return out
}

func cloneCooldowns(cooldowns map[Coord]CooldownMark) map[Coord]CooldownMark {
	out := make(map[Coord]CooldownMark, len(cooldowns))
	for c, mark := range cooldowns { out[c] = mark }
	return out
}

func (e *Engine) clone() *Engine {
	out := *e
	out.board = cloneBoard(e.board)
	out.cooldowns = cloneCooldowns(e.cooldowns)
	out.scores = make(map[string]int, len(e.scores))
	for player, score := range e.scores { out.scores[player] = score }
	out.momentum = cloneInts(e.momentum)
	out.repetitions = make(map[string]int, len(e.repetitions))
	for key, count := range e.repetitions { out.repetitions[key] = count }
	out.history = append([]string(nil), e.history...)
	if e.winner != nil {
		winner := *e.winner
		out.winner = &winner
	}
	return &out
}

func digestText(text string) string {
	digest := sha256.Sum256([]byte(text))
	return fmt.Sprintf("%x", digest[:])
}

func (e *Engine) currentKey() string {
	if e.status != "ongoing" { return e.positionKey("-") }
	return e.positionKey(e.next)
}

func stringPtr(s string) *string { return &s }

func axisOf(cells []Coord) (int, bool) {
	q, r, s := true, true, true
	for _, c := range cells[1:] {
		q = q && c.Q == cells[0].Q
		r = r && c.R == cells[0].R
		s = s && c.Q+c.R == cells[0].Q+cells[0].R
	}
	if q { return 0, true }
	if r { return 1, true }
	if s { return 2, true }
	return -1, false
}

func contiguous(cells []Coord, axis int) bool {
	lo, hi := 0, 0
	for i, c := range cells {
		v := c.Q
		if axis == 0 { v = c.R }
		if i == 0 || v < lo { lo = v }
		if i == 0 || v > hi { hi = v }
	}
	return hi-lo == len(cells)-1
}

func directionParallel(axis int, d Coord) bool {
	switch axis {
	case 0: return d.Q == 0
	case 1: return d.R == 0
	default: return d.Q+d.R == 0
	}
}

func reject(m Move, reason string, e *Engine) Result {
	var next *string
	if e.status == "ongoing" { next = stringPtr(e.next) }
	return Result{
		ID: m.ID, Accepted: false, Reason: stringPtr(reason), MoveType: nil,
		Pushed: 0, Ejected: 0, Momentum: cloneInts(e.momentum),
		NextPlayer: next, PositionKey: e.currentKey(),
	}
}

func (e *Engine) play(m Move) Result {
	if e.status != "ongoing" { return reject(m, "game_over", e) }
	if m.Player != e.next { return reject(m, "wrong_player", e) }
	if len(m.Marbles) == 0 { return reject(m, "empty_selection", e) }
	if len(m.Marbles) > e.in.Rules.MaxGroup { return reject(m, "too_many_marbles", e) }

	cells := make([]Coord, len(m.Marbles))
	selected := make(map[Coord]bool, len(cells))
	for i, raw := range m.Marbles {
		c := Coord{raw[0], raw[1]}
		if selected[c] { return reject(m, "duplicate_marble", e) }
		selected[c] = true
		cells[i] = c
	}
	for _, c := range cells {
		if !e.onBoard(c) || e.board[c] != m.Player { return reject(m, "not_owned", e) }
	}
	for _, c := range cells {
		if _, cooling := e.cooldowns[c]; cooling { return reject(m, "marble_cooling_down", e) }
	}

	axis := -1
	if len(cells) > 1 {
		var ok bool
		axis, ok = axisOf(cells)
		if !ok { return reject(m, "not_collinear", e) }
		if !contiguous(cells, axis) { return reject(m, "not_contiguous", e) }
	}

	d := vectors[m.Direction]
	moveType := "inline"
	if len(cells) > 1 && !directionParallel(axis, d) { moveType = "sidestep" }
	pushed, ejected := 0, 0
	originalBoard := cloneBoard(e.board)
	originalCooldowns := cloneCooldowns(e.cooldowns)
	originalMomentum := cloneInts(e.momentum)

	if moveType == "sidestep" {
		for _, c := range cells {
			if !e.onBoard(add(c, d)) { return reject(m, "broadside_off_board", e) }
		}
		for _, c := range cells {
			if _, occupied := e.board[add(c, d)]; occupied { return reject(m, "blocked", e) }
		}
		for _, c := range cells { delete(e.board, c) }
		for _, c := range cells { e.board[add(c, d)] = m.Player }
	} else {
		front := cells[0]
		for _, c := range cells {
			if !selected[add(c, d)] { front = c; break }
		}
		ahead := add(front, d)
		if !e.onBoard(ahead) { return reject(m, "own_marble_off_board", e) }
		occupant, occupied := e.board[ahead]
		if occupied && occupant == m.Player { return reject(m, "blocked", e) }
		var opponents []Coord
		if occupied {
			cur := ahead
			other := e.other(m.Player)
			for e.onBoard(cur) && e.board[cur] == other {
				opponents = append(opponents, cur)
				cur = add(cur, d)
			}
			if len(opponents) >= len(cells) { return reject(m, "insufficient_force", e) }
			if e.onBoard(cur) {
				if _, blocked := e.board[cur]; blocked { return reject(m, "blocked", e) }
			} else {
				ejected = 1
			}
			pushed = len(opponents)
			for _, c := range opponents {
				delete(e.board, c)
				delete(e.cooldowns, c)
			}
			for _, c := range opponents {
				if mark, cooling := originalCooldowns[c]; cooling {
					dest := add(c, d)
					if e.onBoard(dest) { e.cooldowns[dest] = mark }
				}
			}
			for _, c := range opponents {
				dest := add(c, d)
				if e.onBoard(dest) { e.board[dest] = other }
			}
		}
		for _, c := range cells { delete(e.board, c) }
		for _, c := range cells { e.board[add(c, d)] = m.Player }
	}

	if e.in.Rules.MomentumCap > 0 && pushed > e.momentum[m.Player] {
		e.board = originalBoard
		e.cooldowns = originalCooldowns
		return reject(m, "insufficient_momentum", e)
	}
	if e.in.Rules.MomentumCap > 0 {
		if pushed > 0 {
			e.momentum[m.Player] -= pushed
		} else {
			e.momentum[m.Player] += len(cells)
			if e.momentum[m.Player] > e.in.Rules.MomentumCap {
				e.momentum[m.Player] = e.in.Rules.MomentumCap
			}
		}
	}

	for c, mark := range e.cooldowns {
		if mark.Player == m.Player {
			if mark.Remaining == 1 {
				delete(e.cooldowns, c)
			} else {
				mark.Remaining--
				e.cooldowns[c] = mark
			}
		}
	}
	if e.in.Rules.TempoCooldown > 0 {
		for _, c := range cells {
			e.cooldowns[add(c, d)] = CooldownMark{Player: m.Player, Remaining: e.in.Rules.TempoCooldown}
		}
	}

	if ejected == 1 { e.scores[m.Player]++ }
	prospectiveNext := e.other(m.Player)
	fingerprint := e.equivalenceKey(prospectiveNext)
	if e.in.Rules.KoWindow > 0 {
		start := len(e.history) - e.in.Rules.KoWindow
		if start < 0 { start = 0 }
		for _, prior := range e.history[start:] {
			if fingerprint == prior {
				e.board = originalBoard
				e.cooldowns = originalCooldowns
				e.momentum = originalMomentum
				if ejected == 1 { e.scores[m.Player]-- }
				return reject(m, "position_repeated", e)
			}
		}
	}
	if ejected == 1 { e.noProgress = 0 } else { e.noProgress++ }
	e.legal++
	e.next = prospectiveNext
	e.history = append(e.history, fingerprint)
	e.repetitions[fingerprint]++
	if e.scores[m.Player] >= e.in.Rules.TargetEjections {
		e.status = "win"
		e.winner = stringPtr(m.Player)
	} else if e.in.Rules.RepetitionLimit > 0 && e.repetitions[fingerprint] >= e.in.Rules.RepetitionLimit {
		e.status = "draw_repetition"
	} else if e.in.Rules.NoProgressLimit > 0 && e.noProgress >= e.in.Rules.NoProgressLimit {
		e.status = "draw_no_progress"
	} else if e.in.Rules.MoveLimit > 0 && e.legal >= e.in.Rules.MoveLimit {
		e.status = "draw_move_limit"
	}

	var next *string
	if e.status == "ongoing" { next = stringPtr(e.next) }
	return Result{
		ID: m.ID, Accepted: true, Reason: nil, MoveType: stringPtr(moveType),
		Pushed: pushed, Ejected: ejected, Momentum: cloneInts(e.momentum),
		NextPlayer: next, PositionKey: e.currentKey(),
	}
}

func actionKey(cells []Coord, direction string) string {
	parts := make([]string, len(cells))
	for i, cell := range cells { parts[i] = fmt.Sprintf("%d,%d", cell.Q, cell.R) }
	return strings.Join(parts, ";") + "@" + direction
}

func (e *Engine) legalSuccessors() []Action {
	if e.status != "ongoing" { return []Action{} }
	owned := make([]Coord, 0)
	for cell, player := range e.board {
		if player == e.next { owned = append(owned, cell) }
	}
	sort.Slice(owned, func(i, j int) bool {
		if owned[i].Q != owned[j].Q { return owned[i].Q < owned[j].Q }
		return owned[i].R < owned[j].R
	})
	maximum := e.in.Rules.MaxGroup
	if maximum > len(owned) { maximum = len(owned) }
	actions := make([]Action, 0)
	for size := 1; size <= maximum; size++ {
		group := make([]Coord, 0, size)
		var choose func(int)
		choose = func(start int) {
			if len(group) == size {
				if size > 1 {
					axis, ok := axisOf(group)
					if !ok || !contiguous(group, axis) { return }
				}
				raw := make([][]int, len(group))
				for i, cell := range group { raw[i] = []int{cell.Q, cell.R} }
				for _, direction := range directionNames {
					child := e.clone()
					result := child.play(Move{Player: e.next, Marbles: raw, Direction: direction})
					if result.Accepted {
						copied := append([]Coord(nil), group...)
						actions = append(actions, Action{
							Key: actionKey(copied, direction), State: child,
							Tactical: result.Pushed > 0,
						})
					}
				}
				return
			}
			needed := size - len(group)
			for index := start; index <= len(owned)-needed; index++ {
				group = append(group, owned[index])
				choose(index + 1)
				group = group[:len(group)-1]
			}
		}
		choose(0)
	}
	sort.Slice(actions, func(i, j int) bool { return actions[i].Key < actions[j].Key })
	return actions
}

func actionDigest(actions []Action) string {
	keys := make([]string, len(actions))
	for i, action := range actions { keys[i] = action.Key }
	return digestText(strings.Join(keys, "\n"))
}

func (counts *LeafCounts) add(other LeafCounts) {
	counts.WinPlayer0 += other.WinPlayer0
	counts.WinPlayer1 += other.WinPlayer1
	counts.DrawRepetition += other.DrawRepetition
	counts.DrawNoProgress += other.DrawNoProgress
	counts.DrawMoveLimit += other.DrawMoveLimit
	counts.Horizon += other.Horizon
	counts.Stalled += other.Stalled
}

func (counts *LeafCounts) set(kind string) {
	switch kind {
	case "win_player0": counts.WinPlayer0 = 1
	case "win_player1": counts.WinPlayer1 = 1
	case "draw_repetition": counts.DrawRepetition = 1
	case "draw_no_progress": counts.DrawNoProgress = 1
	case "draw_move_limit": counts.DrawMoveLimit = 1
	case "horizon": counts.Horizon = 1
	case "stalled": counts.Stalled = 1
	}
}

func (e *Engine) leafKind() string {
	if e.status == "win" {
		if e.winner != nil && *e.winner == e.in.Players[0] { return "win_player0" }
		return "win_player1"
	}
	if e.status != "ongoing" { return e.status }
	return ""
}

func compareUtility(left, right Utility) int {
	if left.Outcome != right.Outcome {
		if left.Outcome < right.Outcome { return -1 }
		return 1
	}
	if left.Margin != right.Margin {
		if left.Margin < right.Margin { return -1 }
		return 1
	}
	if left.Momentum != right.Momentum {
		if left.Momentum < right.Momentum { return -1 }
		return 1
	}
	if left.Tempo != right.Tempo {
		if left.Tempo < right.Tempo { return -1 }
		return 1
	}
	return 0
}

func (e *Engine) leafUtility(kind string, remaining int) Utility {
	utility := Utility{
		Margin: e.scores[e.in.Players[0]] - e.scores[e.in.Players[1]],
		Momentum: e.momentum[e.in.Players[0]] - e.momentum[e.in.Players[1]],
	}
	switch kind {
	case "win_player0":
		utility.Outcome = 1
		utility.Tempo = remaining
	case "win_player1":
		utility.Outcome = -1
		utility.Tempo = -remaining
	}
	return utility
}

func continuationNode(
	e *Engine,
	remaining int,
	quiescenceRemaining int,
	inQuiescence bool,
	captureRoot bool,
) Proof {
	kind := e.leafKind()
	var actions []Action
	extension := false
	if kind == "" && remaining > 0 {
		actions = e.legalSuccessors()
		if len(actions) == 0 { kind = "stalled" }
	} else if kind == "" && quiescenceRemaining == 0 {
		kind = "horizon"
	} else if kind == "" {
		for _, action := range e.legalSuccessors() {
			if action.Tactical { actions = append(actions, action) }
		}
		if len(actions) == 0 {
			kind = "horizon"
		} else {
			extension = true
		}
	}
	if kind != "" {
		counts := LeafCounts{}
		counts.set(kind)
		utility := e.leafUtility(kind, remaining)
		preimage := fmt.Sprintf(
			"L\n%d\nquiescence=%d\n%s\n%s\nlegal=%d\nno_progress=%d",
			remaining, quiescenceRemaining, kind, e.currentKey(), e.legal, e.noProgress,
		)
		quiescenceNodes := 0
		if inQuiescence { quiescenceNodes = 1 }
		return Proof{
			Nodes: 1, QuiescenceNodes: quiescenceNodes,
			Leaves: 1, LeafCounts: counts, Value: utility.Outcome, Utility: utility,
			OptimalActions: []string{}, PrincipalVariation: []string{},
			RootAnalyses: []RootAnalysis{}, Digest: digestText(preimage),
		}
	}

	proof := Proof{
		Nodes: 1, OptimalActions: []string{},
		PrincipalVariation: []string{}, RootAnalyses: []RootAnalysis{},
	}
	if inQuiescence { proof.QuiescenceNodes = 1 }
	children := make([]Proof, len(actions))
	lines := []string{
		"N", fmt.Sprintf("%d", remaining),
		fmt.Sprintf("quiescence=%d", quiescenceRemaining),
		e.currentKey(), fmt.Sprintf("legal=%d", e.legal),
		fmt.Sprintf("no_progress=%d", e.noProgress),
	}
	for i, action := range actions {
		childRemaining := remaining - 1
		childQuiescence := quiescenceRemaining
		childInQuiescence := inQuiescence
		if extension {
			childRemaining = 0
			childQuiescence--
			childInQuiescence = true
		}
		child := continuationNode(
			action.State, childRemaining, childQuiescence, childInQuiescence, false,
		)
		children[i] = child
		proof.Nodes += child.Nodes
		proof.QuiescenceNodes += child.QuiescenceNodes
		proof.Leaves += child.Leaves
		proof.LeafCounts.add(child.LeafCounts)
		lines = append(lines, action.Key+" "+child.Digest)
		if captureRoot {
			proof.RootAnalyses = append(proof.RootAnalyses, RootAnalysis{
				Action: action.Key, Nodes: child.Nodes,
				QuiescenceNodes: child.QuiescenceNodes,
				Leaves: child.Leaves, LeafCounts: child.LeafCounts, Utility: child.Utility,
				PrincipalVariation: child.PrincipalVariation, Digest: child.Digest,
			})
		}
	}
	proof.Utility = children[0].Utility
	for _, child := range children[1:] {
		comparison := compareUtility(child.Utility, proof.Utility)
		if e.next == e.in.Players[0] && comparison > 0 { proof.Utility = child.Utility }
		if e.next == e.in.Players[1] && comparison < 0 { proof.Utility = child.Utility }
	}
	for i, child := range children {
		if compareUtility(child.Utility, proof.Utility) == 0 {
			proof.OptimalActions = append(proof.OptimalActions, actions[i].Key)
			if len(proof.PrincipalVariation) == 0 {
				proof.PrincipalVariation = append([]string{actions[i].Key}, child.PrincipalVariation...)
			}
		}
	}
	proof.Value = proof.Utility.Outcome
	proof.Digest = digestText(strings.Join(lines, "\n"))
	return proof
}

func main() {
	raw, err := os.ReadFile("/app/input/match.json")
	if err != nil { panic(err) }
	var in Input
	if err := json.Unmarshal(raw, &in); err != nil { panic(err) }
	e := Engine{
		in: in, board: map[Coord]string{}, cooldowns: map[Coord]CooldownMark{},
		scores: map[string]int{}, momentum: map[string]int{},
		next: in.Initial.NextPlayer, status: "ongoing", repetitions: map[string]int{},
	}
	for _, p := range in.Players {
		e.scores[p] = in.Initial.Ejections[p]
		e.momentum[p] = in.Initial.Momentum[p]
	}
	for _, m := range in.Initial.Marbles { e.board[Coord{m.Q, m.R}] = m.Player }
	for _, c := range in.Initial.Cooldowns {
		e.cooldowns[Coord{c.Q, c.R}] = CooldownMark{Player: c.Player, Remaining: c.Remaining}
	}
	initialFingerprint := e.equivalenceKey(e.next)
	e.repetitions[initialFingerprint] = 1
	e.history = []string{initialFingerprint}

	report := Report{Results: make([]Result, 0, len(in.Moves))}
	for _, m := range in.Moves {
		result := e.play(m)
		actions := e.legalSuccessors()
		result.LegalActionCount = len(actions)
		result.LegalActionDigest = actionDigest(actions)
		report.Results = append(report.Results, result)
	}
	var next *string
	if e.status == "ongoing" { next = stringPtr(e.next) }
	report.Final = Final{
		Status: e.status, Winner: e.winner, LegalMoves: e.legal,
		NoProgress: e.noProgress, Ejections: cloneInts(e.scores),
		Momentum: cloneInts(e.momentum), Cooldowns: e.cooldownList(),
		NextPlayer: next, PositionKey: e.currentKey(), Board: e.boardList(),
	}
	rootActions := e.legalSuccessors()
	proof := continuationNode(
		&e, in.Rules.ContinuationDepth, in.Rules.QuiescenceDepth, false, true,
	)
	report.Continuation = Continuation{
		Depth: in.Rules.ContinuationDepth,
		QuiescenceDepth: in.Rules.QuiescenceDepth,
		RootActionCount: len(rootActions), RootAnalyses: proof.RootAnalyses,
		Nodes: proof.Nodes, QuiescenceNodes: proof.QuiescenceNodes,
		Leaves: proof.Leaves, LeafCounts: proof.LeafCounts,
		Value: proof.Value, Utility: proof.Utility,
		OptimalActions: proof.OptimalActions,
		PrincipalVariation: proof.PrincipalVariation, Digest: proof.Digest,
	}

	if err := os.MkdirAll("/app/output", 0755); err != nil { panic(err) }
	out, err := json.MarshalIndent(report, "", "  ")
	if err != nil { panic(err) }
	if err := os.WriteFile("/app/output/report.json", out, 0644); err != nil { panic(err) }
}
GO

cd /app
/usr/local/go/bin/gofmt -w main.go
/usr/local/go/bin/go build -o /app/abalone .
