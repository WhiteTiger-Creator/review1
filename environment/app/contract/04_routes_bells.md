# 04 — Routes, bells, promotions, handoff

## `corridors.tsv`

Header: `runner_id	from_node	to_node	travel_minutes`

- Directed edges; travel is a non-negative integer (negatives unsafe).
- Duplicate parallel edges (same runner/from/to): keep **minimum** travel.
- Every runner starts at `NOC`. Each surviving beacon needs a route to
  `location`.
- **Per runner (taxes ignored):** travel-shortest path; ties → fewer hops;
  then lexicographically smallest path. Never rank a runner's paths by
  hop/hold/depth taxes. Longer travel with fewer hops loses if shorter travel
  exists.
- **Across runners:** score each runner's *kept* path by **handoff minute**
  (formula below). Do **not** pick by raw travel. Smallest handoff; ties →
  smaller `runner_id`; then smaller path text.
- Path text joins nodes with `>` (e.g. `NOC>HALL-A>WING-B`).
- Unreachable location is unsafe.
- NOTE=`MASK-HOLD` only for **local** mask (`masked=1` on own zone); else
  `DELIVER`.
- Printed **TRAVEL** = corridor sum only; taxes appear only in **HANDOFF**.

Example (`hop_penalty=50`, `hop_waiver=0`): `NOC>MID>X` travel 2 vs `NOC>X`
travel 5 → keep travel-2 path. TRAVEL=`2`; HANDOFF uses `panel+2+2*50`.

## Masked depth (handoff tax only)

`masked_depth` = count of masked zones from the lamp's own zone up through
ancestors (inclusive). Unmasked ancestors add 0. Root-only mask on a tall
tree → depth 1. Do **not** use raw parent-link count.

## Handoff minute

```
panel_minute
  + travel_minutes
  + max(0, count_of_'>' - hop_waiver) * hop_penalty
  + (hold_surcharge if BLACKOUT is MASKED and NOT in grace)
  + (masked_depth * depth_penalty if NOTE is MASK-HOLD, else 0)
```

Widths fields: see 05_render.md. Path `NOC>A>B` has two `>`; `hop_waiver=1`
bills one hop.

**Note / hold / depth:**
- Inherited-only MASKED → `NOTE=DELIVER`; pays hold when MASKED outside grace;
  **no** depth tax.
- Local MASKED → `NOTE=MASK-HOLD`; pays depth tax and hold (unless grace).
- Grace waives **hold only**; hop tax and depth tax still apply.

## `bells.tsv`

Header: `severity	color	priority	bell_name	tie_rule`

- Lower priority is calmer.
- Match (possibly promoted) severity + color; grace: ignore severity, match
  color only.
- Tied lowest priority: every tied row needs the same non-empty `tie_rule`
  other than `-`; append `<body>[tie:<rule>]` with no space; pick smallest
  `bell_name`.
- No matching row is unsafe.

## `promotions.tsv`

Header: `age_threshold	severity_from	severity_to`

After grace, before bells. Loudness: HIGH > MED > LOW.

- Non-negative thresholds; severities LOW/MED/HIGH.
- In grace: skip entirely.
- Else match on **span age** (primary window; 03_alarms.md), not board age /
  not collapsed max-last. Strict: `span_age > age_threshold`.
- Among matches for primary severity: largest `age_threshold`; threshold ties →
  **quietest** `severity_to`. No chaining. Demotion allowed.
