#!/bin/bash
set -euo pipefail

cd /app

python3 - <<'PY'
from pathlib import Path

path = Path("/app/internal/season/config.go")
text = path.read_text()
old = '''func SoftBaseline() Rules {
	return Rules{
		RunID:       "tak-legacy",
		BoardSize:   5,
		RoadOrtho:   0,
		CapsOnRoad:  0,
		CapsOnFlat:  0,
		WallsOnFlat: 1,
		FlatMargin:  6,
		WinPoints:   2,
		DrawPoints:  0,
	}
}'''
new = '''func SoftBaseline() Rules {
	return Rules{
		RunID:       "tak-champ-v1",
		BoardSize:   5,
		RoadOrtho:   1,
		CapsOnRoad:  1,
		CapsOnFlat:  1,
		WallsOnFlat: 0,
		FlatMargin:  3,
		WinPoints:   3,
		DrawPoints:  1,
	}
}'''
assert old in text, "SoftBaseline not found"
text = text.replace(old, new, 1)

old = '''func clubWeekendFallback(r *Rules) {
	r.RoadOrtho = 0
	r.CapsOnRoad = 0
	r.CapsOnFlat = 0
	r.WallsOnFlat = 1
	r.FlatMargin = 9
	r.WinPoints = 2
	r.DrawPoints = 0
}

func applyHeatOverlay(configDir, profile string, r *Rules) {
	overlay := filepath.Join(configDir, "runtime", heatFloorName(profile))
	m, err := parseTOML(overlay)
	if err != nil {
		clubWeekendFallback(r)
		return
	}
	if _, ok := m["road_ortho"]; ok {
		r.RoadOrtho = atoiDefault(m, "road_ortho", r.RoadOrtho)
	}
	if _, ok := m["caps_on_road"]; ok {
		r.CapsOnRoad = atoiDefault(m, "caps_on_road", r.CapsOnRoad)
	}
	if _, ok := m["caps_on_flat"]; ok {
		r.CapsOnFlat = atoiDefault(m, "caps_on_flat", r.CapsOnFlat)
	}
	if _, ok := m["walls_on_flat"]; ok {
		r.WallsOnFlat = atoiDefault(m, "walls_on_flat", r.WallsOnFlat)
	}
	if _, ok := m["flat_margin"]; ok {
		r.FlatMargin = atoiDefault(m, "flat_margin", r.FlatMargin)
	}
	if _, ok := m["win_points"]; ok {
		r.WinPoints = atoiDefault(m, "win_points", r.WinPoints)
	}
	if _, ok := m["draw_points"]; ok {
		r.DrawPoints = atoiDefault(m, "draw_points", r.DrawPoints)
	}
}'''
new = '''func clubWeekendFallback(r *Rules) {
	_ = r
}

func applyHeatOverlay(configDir, profile string, r *Rules) {
	_ = configDir
	_ = profile
	_ = r
}'''
assert old in text, "applyHeatOverlay/clubWeekendFallback not found"
text = text.replace(old, new, 1)

old = '''func profileRoot(configDir string) string {
	// Exhibition root; championship uses config/profiles.
	root := filepath.Join(configDir, "profiles.legacy")
	if v := os.Getenv("TAK_PROFILE_ROOT"); v != "" {
		root = v
	}
	return root
}'''
new = '''func profileRoot(configDir string) string {
	root := filepath.Join(configDir, "profiles")
	if v := os.Getenv("TAK_PROFILE_ROOT"); v != "" {
		root = v
	}
	return root
}'''
assert old in text, "profileRoot not found"
path.write_text(text.replace(old, new, 1))

path = Path("/app/internal/pathing/road.go")
text = path.read_text()
old = '''	if p.Kind == "cap" {
		// Exhibition latch: treat caps_on_road==0 as armed.
		return rules.CapsOnRoad == 0
	}'''
new = '''	if p.Kind == "cap" {
		return rules.CapsOnRoad == 1
	}'''
assert old in text, "caps_on_road latch not found"
text = text.replace(old, new, 1)

old = '''	// Exhibition polarity: RoadOrtho==1 means diagonals allowed.
	orthoOnly := rules.RoadOrtho == 0'''
new = '''	orthoOnly := rules.RoadOrtho == 1'''
assert old in text, "road ortho polarity not found"
text = text.replace(old, new, 1)

old = '''func PlayerAxes() (RoadAxis, RoadAxis) {
	return AxisEW, AxisNS
}'''
new = '''func PlayerAxes() (RoadAxis, RoadAxis) {
	return AxisNS, AxisEW
}'''
assert old in text, "PlayerAxes not found"
path.write_text(text.replace(old, new, 1))

path = Path("/app/internal/flats/count.go")
text = path.read_text()
old = '''	case "cap":
		// Exhibition: caps excluded when sealed caps_on_flat is 1.
		return rules.CapsOnFlat == 0
	case "wall":
		// Exhibition always tallies walls as flats for the house sheet.
		return true'''
new = '''	case "cap":
		return rules.CapsOnFlat == 1
	case "wall":
		return rules.WallsOnFlat == 1'''
assert old in text, "flat counting latch not found"
text = text.replace(old, new, 1)

old = '''	_ = rules.WallsOnFlat
	return total
}'''
new = '''	return total
}'''
assert old in text, "WallsOnFlat discard not found"
path.write_text(text.replace(old, new, 1))

path = Path("/app/internal/victory/decide.go")
text = path.read_text()
old = '''const MarginPad = 3'''
new = '''const MarginPad = 0'''
assert old in text, "MarginPad not found"
text = text.replace(old, new, 1)

old = '''	// Exhibition gate order: flats before roads.
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
}'''
new = '''	_ = MarginPad
	if roadA && !roadB {
		out.Winner, out.Reason = "A", "road_complete"
		return out
	}
	if roadB && !roadA {
		out.Winner, out.Reason = "B", "road_complete"
		return out
	}
	if roadA && roadB {
		if fa > fb {
			out.Winner, out.Reason = "A", "road_complete"
		} else if fb > fa {
			out.Winner, out.Reason = "B", "road_complete"
		} else {
			out.Winner, out.Reason = "draw", "mutual_draw"
		}
		return out
	}
	diff := abs(fa - fb)
	if diff >= rules.FlatMargin {
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
	out.Winner, out.Reason = "draw", "mutual_draw"
	return out
}'''
assert old in text, "Decide gates not found"
path.write_text(text.replace(old, new, 1))

path = Path("/app/internal/bracket/report.go")
text = path.read_text()
old = '''var priorityScale = 1.0'''
new = '''var priorityScale = 1.20'''
assert old in text, "priorityScale not found"
text = text.replace(old, new, 1)

old = '''func Polish(matches []MatchRow, rules season.Rules) []MatchRow {
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
}'''
new = '''func Polish(matches []MatchRow, rules season.Rules) []MatchRow {
	out := make([]MatchRow, len(matches))
	copy(out, matches)
	_ = rules
	return out
}'''
assert old in text, "Polish not found"
text = text.replace(old, new, 1)

old = '''	sort.Slice(order, func(i, j int) bool {
		ai, aj := tab[order[i]], tab[order[j]]
		if ai.flatDiff != aj.flatDiff {
			return ai.flatDiff > aj.flatDiff
		}
		if ai.points != aj.points {
			return ai.points > aj.points
		}
		return order[i] < order[j]
	})'''
new = '''	sort.Slice(order, func(i, j int) bool {
		ai, aj := tab[order[i]], tab[order[j]]
		if ai.points != aj.points {
			return ai.points > aj.points
		}
		if ai.flatDiff != aj.flatDiff {
			return ai.flatDiff > aj.flatDiff
		}
		return order[i] < order[j]
	})'''
assert old in text, "standings sort not found"
text = text.replace(old, new, 1)

old = '''func ReconcileStandings(standings []Standing) []Standing {
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
}'''
new = '''func ReconcileStandings(standings []Standing) []Standing {
	return standings
}'''
assert old in text, "ReconcileStandings not found"
text = text.replace(old, new, 1)

old = '''func FinalizeReport(rep *Report, rules season.Rules) {
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
}'''
new = '''func FinalizeReport(rep *Report, rules season.Rules) {
	_ = rep
	_ = rules
	_ = victory.MarginPad
}'''
assert old in text, "FinalizeReport not found"
path.write_text(text.replace(old, new, 1))

seal = "cc7af441d8baf8187d315a615cbcb3f4424cc5499d54c65e4b590b9a7f4264a8"
Path("/app/config/profiles/champ-v3/rules.toml").write_text(
    "\n".join(
        [
            'run_id = "tak-champ-v1"',
            "board_size = 5",
            "road_ortho = 1",
            "caps_on_road = 1",
            "caps_on_flat = 1",
            "walls_on_flat = 0",
            "flat_margin = 3",
            "win_points = 3",
            "draw_points = 1",
            f'config_seal = "{seal}"',
            "",
        ]
    )
)
# Neutralize overlay so presence cannot clobber if someone re-enables apply.
Path("/app/config/runtime/champ-v3.floor.toml").write_text(
    "# championship floors are sealed; overlay must not retune them\n"
)
print("tak championship ruleset aligned")
PY

go build -o /app/bin/tak-road /app/cmd/tak-road
/app/bin/tak-road --scenarios /app/scenarios --config /app/config --out /app/output
