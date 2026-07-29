# 03 — Alarms: flaps, collapse, acknowledgements

## `flaps.tsv`

Header: `flap_id	lamp_id	first_minute	last_minute	severity	raw_text	clock_id`

- Unknown `lamp_id` is unsafe.
- Every raw row must satisfy `first_minute <= last_minute`; reversed windows are
  unsafe (checked before collapse).
- Collapse rows that share the same `lamp_id` and identical `raw_text`:
  - `first_minute` = minimum among contributors
  - `last_minute` = maximum among contributors
  - **Primary** contributor = earliest `first_minute`; if tied, lexicographically
    smaller `flap_id`
  - `severity` and `clock_id` come from the primary only (never pick the loudest
    severity on a first-minute tie)
- **Active window is half-open on the right:**
  `first_minute <= panel_minute < last_minute`.
  - Example: first=100, last=120 → active at 100..119; **inactive at 120**.

### Two ages (do not conflate)

- **Board age** (printed AGE column) =
  `panel_minute - first_minute`
  using the collapsed `first_minute` (the minimum). Canonical decimal.
- **Span age** (promotion only) =
  `primary_last_minute - first_minute`
  where `primary_last_minute` is the **primary contributor row's own**
  `last_minute`, not the collapsed maximum last. A later contributor may extend
  the active window without widening promotion span. Span age does **not**
  depend on `panel_minute`.

## `acknowledgements.tsv`

Header: `flap_id	operator_id	ack_minute	grace_minutes	clock_id`

- Every `flap_id` must appear on at least one flap row; unknown flap ids are
  unsafe.
- Every `operator_id` must appear in `operators.tsv` (see 02_catalog.md).
- After collapse, an ack applies if it names any contributing flap id
  (including non-primary contributors).
- Early-ack uses the collapsed alarm's `first_minute` (the minimum across
  contributors), not the named row's first_minute alone.
- Ack before that collapsed first_minute is unsafe.
- Grace window shape is half-open on the right:
  `ack_minute <= panel_minute < ack_minute + grace_minutes`.
  - `grace_minutes=0` yields an empty window (never suppresses).

### Which ack decides grace

If several acknowledgements belong to the collapsed alarm:

1. Start from acks with `ack_minute <= panel_minute`.
2. **Contributor gate (separate from early-ack):** an ack naming a
   **non-primary** contributor is eligible for grace only when
   `ack_minute >=` that contributor row's own `first_minute`. Acks naming the
   primary flap skip this gate (early-ack already used collapsed first).
   Ineligible secondary acks are dropped before step 3.
3. Choose exactly one among remaining eligible: largest `ack_minute`; if tied,
   largest `grace_minutes`; if still tied, lexicographically largest `flap_id`.
4. The alarm is in grace **only** if that chosen ack's window covers
   `panel_minute`. Older acks are ignored even if their windows would still
   cover the minute.

Outside grace, normal (possibly promoted) severity escalation applies.
