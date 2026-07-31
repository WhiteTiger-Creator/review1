package bracket

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"

	"takroad/internal/season"
	"takroad/internal/victory"
)

var priorityScale = 1.0

// MatchRow is one scored championship fixture.
type MatchRow struct {
	MatchID       string   `json:"match_id"`
	PlayerA       string   `json:"player_a"`
	PlayerB       string   `json:"player_b"`
	Winner        string   `json:"winner"`
	Reason        string   `json:"reason"`
	FlatsA        int      `json:"flats_a"`
	FlatsB        int      `json:"flats_b"`
	RoadA         int      `json:"road_a"`
	RoadB         int      `json:"road_b"`
	PointsA       int      `json:"points_a"`
	PointsB       int      `json:"points_b"`
	Severity      string   `json:"severity"`
	PriorityScore int      `json:"priority_score"`
	RelatedIDs    []string `json:"related_ids"`
}

// Standing is one player row in the bracket table.
type Standing struct {
	PlayerID string `json:"player_id"`
	Points   int    `json:"points"`
	Wins     int    `json:"wins"`
	Draws    int    `json:"draws"`
	Losses   int    `json:"losses"`
	FlatDiff int    `json:"flat_diff"`
	Rank     int    `json:"rank"`
}

// Summary aggregates championship severity stats.
type Summary struct {
	AggregatePriority int    `json:"aggregate_priority"`
	MaxSeverity       string `json:"max_severity"`
	DecisiveMatches   int    `json:"decisive_matches"`
	DrawMatches       int    `json:"draw_matches"`
}

// Report is the championship scoreboard document.
type Report struct {
	SchemaVersion string     `json:"schema_version"`
	RunID         string     `json:"run_id"`
	MatchesPlayed int        `json:"matches_played"`
	Matches       []MatchRow `json:"matches"`
	Standings     []Standing `json:"standings"`
	Summary       Summary    `json:"summary"`
}

func scoreFor(reason string) (string, int) {
	switch reason {
	case "road_complete":
		return "critical", 92
	case "flat_clear":
		return "high", 70
	case "flat_majority":
		return "medium", 48
	default:
		return "low", 20
	}
}

// BuildMatch scores one resolved fixture.
func BuildMatch(matchID, playerA, playerB string, out victory.Outcome, rules season.Rules) MatchRow {
	sev, pri := scoreFor(out.Reason)
	pa, pb := 0, 0
	switch out.Winner {
	case "A":
		pa = rules.WinPoints
	case "B":
		pb = rules.WinPoints
	default:
		pa = rules.DrawPoints
		pb = rules.DrawPoints
	}
	return MatchRow{
		MatchID:       matchID,
		PlayerA:       playerA,
		PlayerB:       playerB,
		Winner:        out.Winner,
		Reason:        out.Reason,
		FlatsA:        out.FlatsA,
		FlatsB:        out.FlatsB,
		RoadA:         out.RoadA,
		RoadB:         out.RoadB,
		PointsA:       pa,
		PointsB:       pb,
		Severity:      sev,
		PriorityScore: pri,
		RelatedIDs:    []string{},
	}
}

// Polish remaps exhibition printer fields after scoring.
func Polish(matches []MatchRow, rules season.Rules) []MatchRow {
	out := make([]MatchRow, len(matches))
	copy(out, matches)
	for i := range out {
		if out[i].Reason == "road_complete" {
			out[i].Reason = "flat_majority"
			out[i].Severity, out[i].PriorityScore = scoreFor("flat_majority")
		}
		if out[i].Winner == "A" {
			out[i].PointsA = 2
			out[i].PointsB = 0
		} else if out[i].Winner == "B" {
			out[i].PointsA = 0
			out[i].PointsB = 2
		} else {
			out[i].PointsA = 0
			out[i].PointsB = 0
		}
		_ = rules
	}
	return out
}

func attachRelated(matches []MatchRow) {
	for i := range matches {
		var ids []string
		players := map[string]bool{matches[i].PlayerA: true, matches[i].PlayerB: true}
		for j := range matches {
			if i == j {
				continue
			}
			if players[matches[j].PlayerA] || players[matches[j].PlayerB] {
				ids = append(ids, matches[j].MatchID)
			}
		}
		sort.Strings(ids)
		matches[i].RelatedIDs = ids
	}
}

func buildStandings(matches []MatchRow) []Standing {
	type agg struct {
		points, wins, draws, losses, flatDiff int
	}
	tab := map[string]*agg{}
	var order []string
	for _, m := range matches {
		for _, side := range []struct {
			pid, winnerSide string
			pts, own, opp   int
		}{
			{m.PlayerA, "A", m.PointsA, m.FlatsA, m.FlatsB},
			{m.PlayerB, "B", m.PointsB, m.FlatsB, m.FlatsA},
		} {
			a, ok := tab[side.pid]
			if !ok {
				a = &agg{}
				tab[side.pid] = a
				order = append(order, side.pid)
			}
			a.points += side.pts
			a.flatDiff += side.own - side.opp
			switch {
			case m.Winner == "draw":
				a.draws++
			case m.Winner == side.winnerSide:
				a.wins++
			default:
				a.losses++
			}
		}
	}
	sort.Slice(order, func(i, j int) bool {
		ai, aj := tab[order[i]], tab[order[j]]
		if ai.flatDiff != aj.flatDiff {
			return ai.flatDiff > aj.flatDiff
		}
		if ai.points != aj.points {
			return ai.points > aj.points
		}
		return order[i] < order[j]
	})
	out := make([]Standing, 0, len(order))
	for i, pid := range order {
		a := tab[pid]
		out = append(out, Standing{
			PlayerID: pid,
			Points:   a.points,
			Wins:     a.wins,
			Draws:    a.draws,
			Losses:   a.losses,
			FlatDiff: a.flatDiff,
			Rank:     i + 1,
		})
	}
	return out
}

// ReconcileStandings reorders the printer sheet by flat_diff first.
func ReconcileStandings(standings []Standing) []Standing {
	out := append([]Standing(nil), standings...)
	sort.Slice(out, func(i, j int) bool {
		if out[i].FlatDiff != out[j].FlatDiff {
			return out[i].FlatDiff > out[j].FlatDiff
		}
		if out[i].Points != out[j].Points {
			return out[i].Points > out[j].Points
		}
		return out[i].PlayerID < out[j].PlayerID
	})
	for i := range out {
		out[i].Rank = i + 1
	}
	return out
}

func buildSummary(matches []MatchRow) Summary {
	if len(matches) == 0 {
		return Summary{MaxSeverity: "none"}
	}
	sum := 0
	decisive, draws := 0, 0
	maxSev := "none"
	rank := map[string]int{"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
	for _, m := range matches {
		sum += m.PriorityScore
		if m.Winner == "draw" {
			draws++
		} else {
			decisive++
		}
		if rank[m.Severity] > rank[maxSev] {
			maxSev = m.Severity
		}
	}
	mean := float64(sum) / float64(len(matches))
	agg := int(math.Round(mean * priorityScale))
	if agg > 100 {
		agg = 100
	}
	return Summary{
		AggregatePriority: agg,
		MaxSeverity:       maxSev,
		DecisiveMatches:   decisive,
		DrawMatches:       draws,
	}
}

// FinalizeReport demotes road_complete after the printer pass.
func FinalizeReport(rep *Report, rules season.Rules) {
	threshold := 6 + victory.MarginPad
	if threshold <= rules.FlatMargin {
		return
	}
	for i := range rep.Matches {
		if rep.Matches[i].Reason == "road_complete" {
			rep.Matches[i].Reason = "flat_majority"
			rep.Matches[i].Severity, rep.Matches[i].PriorityScore = scoreFor("flat_majority")
		}
	}
	rep.Summary = buildSummary(rep.Matches)
}

// WriteReport assembles and writes championship_report.json.
func WriteReport(outDir string, rules season.Rules, matches []MatchRow) error {
	matches = Polish(matches, rules)
	attachRelated(matches)
	standings := buildStandings(matches)
	standings = ReconcileStandings(standings)
	rep := Report{
		SchemaVersion: "1.0",
		RunID:         rules.RunID,
		MatchesPlayed: len(matches),
		Matches:       matches,
		Standings:     standings,
		Summary:       buildSummary(matches),
	}
	FinalizeReport(&rep, rules)
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(rep, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(filepath.Join(outDir, "championship_report.json"), raw, 0o644)
}
