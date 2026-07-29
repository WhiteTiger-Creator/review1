# 05 — Render, silence, sorting, processing order

## `widths.tsv`

Header: `field	width`

Required positive column widths: `beacon_lamp`, `beacon_color`, `beacon_zone`,
`beacon_age`, `beacon_bell`, `beacon_blackout`, `beacon_message`, `runner_id`,
`runner_lamp`, `runner_path`, `runner_travel`, `runner_handoff`, `runner_note`.

Also required (non-negative integers; zero allowed; missing/negative unsafe):

- `hop_penalty` — minutes charged per billed hop (see hop_waiver)
- `hop_waiver` — first N `>` characters in the path are free
  (`billed_hops = max(0, count('>') - hop_waiver)`)
- `hold_surcharge` — when printed BLACKOUT is `MASKED` and not in grace
- `depth_penalty` — per `masked_depth` (see 04_routes_bells.md)

Non-positive column widths are unsafe.

## Message assembly (order matters)

1. Start from the flap `raw_text`.
2. If the lamp has a **local** mask, prefix `*` with no space.
   Inherited-only MASKED lamps do **not** get the asterisk.
3. If a bell tie rule applies, append `[tie:<rule>]` with no separating space.
4. Width-check the final string against `beacon_message` for **every** active
   lamp **before** silence suppression. Overflow on a lamp that silence would
   later drop still makes the board unsafe.

## `beacon.queue`

Header labels: `LAMP`, `COLOR`, `ZONE`, `AGE`, `BELL`, `BLACKOUT`, `MESSAGE`.

- AGE prints **board age** (`panel_minute - first_minute`), not span age.
- Sort by: **board age** descending, then MASKED before CLEAR, then `lamp_id`
  ascending. Do **not** sort by span age (a larger span can still sort later).
- Silence-group suppression when two or more active lamps share a
  `silence_group`:
  1. Drop every CLEAR beacon **only if** the group contains at least one
     **local** MASKED lamp. Inherited-only MASKED does **not** suppress CLEAR
     peers (both may publish).
  2. Among MASKED beacons in the group, if any have a **local** mask, discard
     inherited-only MASKED peers first.
  3. If more than one MASKED remains after step 2, keep **exactly one**:
     largest **board age**; ages tie → lexicographically smallest `lamp_id`.
     Do not use span age. Never publish two local MASKED peers from one group.
  Local mask outranks age (step 2 before step 3).

## `runner.fold`

Header labels: `RUNNER`, `LAMP`, `PATH`, `TRAVEL`, `HANDOFF`, `NOTE`.

- One row per published beacon.
- **TRAVEL** = corridor travel only; **HANDOFF** = full handoff minute (taxes
  included). They differ whenever any hop/hold/depth tax is nonzero.
- Sort by numeric handoff ascending, then `runner_id`, then path, then lamp id.
  Grace-waived hold and `masked_depth` taxes can reorder rows.

## Empty active board

Zero active flaps still writes header-only products.

## Mandatory processing order

1. Resolve/validate OUT; scrub OUT to `.keep` only (see 01_invoke.md).
2. Load tables; reject FORCE_FAIL.
3. Validate clocks, lamps, windows, acks, operators.
4. Build zones; inherited vs local mask; masked_depth.
5. Collapse flaps; early-ack check.
6. Active alarms (half-open last); board age and span age.
7. Grace via latest eligible ack (contributor gate; see 03_alarms.md).
8. Promote using **span age** (skip if in grace).
9. Choose bells.
10. Build fields: BLACKOUT inherited; `*` local only; tie marker.
11. Width-check **all** active messages (pre-silence).
12. Silence (CLEAR drop needs local MASKED; then local filter; max board age).
13. Route: per-runner travel path, across-runners by handoff score.
14. Handoff taxes: billed hops + hold(unless grace) + depth(local only).
15. Sort; write products; final OUT hygiene; ensure `.keep`; clean notes.

## Determinism

Input row order must not change products.
