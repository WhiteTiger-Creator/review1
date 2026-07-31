# Tak Road / Flat Championship Ruleset (champ-v3)

This document is the sealed operator contract for `tak-road`. Bracket sheets,
heat overlays, and printer passes are subordinate to it. Scoring (§6) depends
on gates (§5), which depend on road and flat detection (§3–§4), which depend
on active floors (§1–§2).

## §1 Sealed floors

Active profile is named by `config/profile.name`. Under
`config/profiles/<name>/rules.toml` use spaced TOML with quoted strings where
applicable. Championship floors:

| key | value |
|---|---|
| run_id | tak-champ-v1 |
| board_size | 5 |
| road_ortho | 1 |
| caps_on_road | 1 |
| caps_on_flat | 1 |
| walls_on_flat | 0 |
| flat_margin | 3 |
| win_points | 3 |
| draw_points | 1 |

`config_seal` must equal the lowercase hex SHA-256 of this exact payload
(trailing newline after each line; seal bytes are not part of the payload):

```
run_id=tak-champ-v1
board_size=5
road_ortho=1
caps_on_road=1
caps_on_flat=1
walls_on_flat=0
flat_margin=3
win_points=3
draw_points=1
```

When `config_seal` does not match, load must not keep exhibition legacy floors.
The in-code baseline used on seal mismatch must carry the same championship
table above (including `run_id` tak-champ-v1).

Profile directory root is `config/profiles` (not `profiles.legacy`). An optional
`TAK_PROFILE_ROOT` override may point at an alternate root for drills, but the
default championship path is `config/profiles`.

## §2 Runtime overlays

After seal accept, files under `config/runtime/<profile.name>.floor.toml` must
not change sealed `road_ortho`, `caps_on_road`, `caps_on_flat`, `walls_on_flat`,
`flat_margin`, `win_points`, or `draw_points`. Absence of that overlay must not
activate a weekend club fallback that retunes those same fields. Scenario
fixtures stay sealed between heats.

## §3 Board model

Board is `board_size` by `board_size` squares. Each occupied cell has a stack
of pieces ordered bottom to top. Only the top piece controls the square.

Piece kinds:

- `flat` — flat stone
- `wall` — standing stone
- `cap` — capstone

Colors are `A` (north-south player) and `B` (east-west player).

## §4 Road detection

A road for color C is a continuous path of squares whose top piece is
road-controlling for C.

Road-controlling pieces:

- top `flat` of color C always controls
- top `cap` of color C controls only when `caps_on_road` is 1
- top `wall` never controls a road for either color

Adjacency: when `road_ortho` is 1, only orthogonal neighbors (N/E/S/W). When
`road_ortho` is 0, diagonals are also allowed. Championship play uses
`road_ortho = 1`.

Axis assignment (USTA convention):

- color `A` connects the north edge (row 0) to the south edge (row board_size-1)
- color `B` connects the west edge (col 0) to the east edge (col board_size-1)

## §5 Flat counts

Flat count for color C is the number of squares whose top piece counts as a
flat for C:

- top `flat` of color C always counts
- top `cap` of color C counts only when `caps_on_flat` is 1
- top `wall` of color C counts only when `walls_on_flat` is 1

Championship play uses `caps_on_flat = 1` and `walls_on_flat = 0`.

## §6 Victory gates (ordered)

Apply exactly one reason, first match wins:

1. `road_complete` — exactly one color has a road on its assigned axis. That
   color wins. If both colors have roads, the higher flat count wins with
   reason `road_complete`; equal flats yield `mutual_draw`.
2. else `flat_clear` — `abs(flats_a - flats_b) >= flat_margin` (active sealed
   margin; no seasonal pad). Winner is the side with the higher flat count.
3. else `flat_majority` — flat counts differ. Winner is the higher flat count.
4. else `mutual_draw`.

Gates after a skipped earlier gate must still see true road flags and flat
counts from §4–§5. A printer pass must not demote `road_complete` after gates
resolve.

## §7 Points, severity, related ids

Winner points: `win_points` to winner, 0 to loser. Draw: `draw_points` each.
No post-score remapping to exhibition 2/0 or 0/0.

| reason | severity | priority_score |
|---|---|---|
| road_complete | critical | 92 |
| flat_clear | high | 70 |
| flat_majority | medium | 48 |
| mutual_draw | low | 20 |

`related_ids` for a match lists every other `match_id` that shares `player_a` or
`player_b` with it, sorted ascending, without duplicates, excluding self.

## §8 Standings

Per player across all matches:

- `points` = sum of points awarded to that player
- `wins` / `draws` / `losses` from that player's perspective
- `flat_diff` = sum of `(own_flats - opponent_flats)` across that player's matches

Sort standings by `points` descending, then `flat_diff` descending, then
`player_id` ascending. Assign `rank` from 1 after sorting. No printer reorder
after the table is built.

## §9 Summary

- `aggregate_priority = min(100, round(mean(priority_score) * 1.20))` with
  half-away-from-zero rounding
- `max_severity` is the highest severity among matches (critical > high >
  medium > low > none)
- `decisive_matches` counts non-draw winners
- `draw_matches` counts draws

## §10 Output schema

Write `/app/output/championship_report.json` with keys:

`schema_version` (`"1.0"`), `run_id`, `matches_played`, `matches`, `standings`,
`summary`.

Each match row: `match_id`, `player_a`, `player_b`, `winner` (`A`|`B`|`draw`),
`reason`, `flats_a`, `flats_b`, `road_a`, `road_b`, `points_a`, `points_b`,
`severity`, `priority_score`, `related_ids`.

Matches are emitted one per fixture sorted ascending by `match_id`.
`matches_played` equals that count. `run_id` equals the sealed profile `run_id`
(or the floor baseline `run_id` on seal mismatch).
