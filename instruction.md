The Tak championship engine at `/app/bin/tak-road` scores static board fixtures under `/app/scenarios/` and writes `/app/output/championship_report.json` via `/app/bin/tak-road --scenarios /app/scenarios --config /app/config --out /app/output`. Rebuild from `/app/` sources. Edit only `/app/internal/season/config.go`, `/app/internal/pathing/road.go`, `/app/internal/flats/count.go`, `/app/internal/victory/decide.go`, `/app/internal/bracket/report.go`, `/app/config/profiles/champ-v3/rules.toml`, and `/app/config/runtime/`. Do not modify scenarios, contracts, docs, cmd, or board. Full road, flat, gate, scoring, and standings rules are in `/app/contracts/championship-ruleset.md`. Note that code comments and docstrings may themselves contain errors.

Bring sealed profile `champ-v3` at `/app/config/profiles/champ-v3/rules.toml` to spaced TOML: `run_id = "tak-champ-v1"`, `board_size = 5`, `road_ortho = 1`, `caps_on_road = 1`, `caps_on_flat = 1`, `walls_on_flat = 0`, `flat_margin = 3`, `win_points = 3`, `draw_points = 1`, `config_seal = "cc7af441d8baf8187d315a615cbcb3f4424cc5499d54c65e4b590b9a7f4264a8"` (SHA-256 of the payload below). Seal mismatch must still use those floors from the in-code baseline. Default profile root is `/app/config/profiles` (not `profiles.legacy`). After seal accept, `/app/config/runtime/<profile.name>.floor.toml` must not override sealed `road_ortho`, `caps_on_road`, `caps_on_flat`, `walls_on_flat`, `flat_margin`, `win_points`, or `draw_points`, and removing that overlay must not activate a weekend fallback that retunes those fields.

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

Engine output must enforce the championship-ruleset for orthogonal-only roads when `road_ortho` is 1, USTA axes (A north-south, B east-west), capstones on roads/flats when armed, walls never on roads and only on flats when `walls_on_flat` is 1, and ordered gates `road_complete` then `flat_clear` then `flat_majority` then `mutual_draw`. Wins award `win_points` (loser 0); draws award `draw_points` each. Severities: critical/92, high/70, medium/48, low/20. `related_ids` share a player, sorted. Standings sort points then `flat_diff` then `player_id`. `aggregate_priority = min(100, round(mean(priority_score)*1.20))`. `decisive_matches` counts non-draws; `draw_matches` counts draws. One row per fixture by `match_id`, `schema_version` `"1.0"`, `run_id` from sealed profile (or baseline on seal mismatch). No post-score remapping of points, reasons, severities, standings order, or summary aggregates. Schema keys: schema_version, run_id, matches_played, matches[{match_id,player_a,player_b,winner,reason,flats_a,flats_b,road_a,road_b,points_a,points_b,severity,priority_score,related_ids}], standings[{player_id,points,wins,draws,losses,flat_diff,rank}], summary[{aggregate_priority,max_severity,decisive_matches,draw_matches}].
