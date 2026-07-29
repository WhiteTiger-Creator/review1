# 02 — Catalog: clock, lamps, blackouts, operators

## `clock.txt`

One line: `<panel_minute> <clock_id>`

`panel_minute` is a non-negative integer. Every timed table row with a
`clock_id` column must match this id; disagreement makes the board unsafe.

## `lamps.tsv`

Header: `lamp_id	rack_pos	color	silence_group	location`

- `rack_pos` is an integer rack slot.
- `location` is the corridor graph node for runner delivery.
- Duplicate `lamp_id` values make the board unsafe.

## `operators.tsv`

Header: `operator_id`

- Lists every operator allowed to acknowledge flaps.
- An acknowledgement whose `operator_id` is absent from this table makes the
  board unsafe.
- Duplicate `operator_id` rows make the board unsafe.

## `blackouts.tsv`

Header: `zone_id	parent_id	rack_lo	rack_hi	masked`

- `masked` must be exactly `0` or `1`; any other value is unsafe.
- Inclusive rack ranges `[rack_lo, rack_hi]`.
- `parent_id` is `-` for a root zone, otherwise another `zone_id`.
- A named parent must exist; missing ancestors are unsafe.
- A cycle in the parent chain is unsafe.
- Any two zones whose ranges intersect are unsafe (pairwise disjoint ranges).
  Parent links are a separate inheritance tree; they do not require nesting.
- Each lamp resolves to the unique zone containing `rack_pos`. No match is
  unsafe. Boundaries are inclusive.

### Three different mask uses (do not conflate)

1. **Inherited mask** — true when the lamp's zone **or any ancestor** has
   `masked=1`. This drives the printed BLACKOUT column (`MASKED` / `CLEAR`),
   silence-group membership, and `hold_surcharge` on handoff.
2. **Local mask** — true only when the lamp's **own** zone row has `masked=1`
   (ancestors do not count). This alone drives the MESSAGE asterisk and the
   runner slip note (`MASK-HOLD` vs `DELIVER`).
3. Therefore a lamp can print `BLACKOUT=MASKED` with a plain (no `*`) MESSAGE,
   `NOTE=DELIVER`, and still pay `hold_surcharge` when only an ancestor is
   masked.
