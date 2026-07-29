# pact_n4

Normative graded-report rules for `/app/output/peak_report.json` produced by the systemd lane unit cgroup memcg path. Same contract as the task prompt.

## Schema

- `schema` must be `peak_v1`
- `cases` is an array of objects with:
  - `slice_id` (string): `oak`, `pine`, `ash`, or `elm`
  - `peak_pages` (int): high-water of attributed residency
  - `budget_cap` (int): `48` on the default arm; `96` when the driver is invoked with the wide arm documented in operators.md
  - `path_mode` (string): `clean`, `mended`, or `reloaded`
  - `harness_exit` (int): `0` when `peak_pages <= budget_cap`, else nonzero

## peak_pages

At each sample tick, sum `pages` for PIDs whose membership maps to the active lane. `peak_pages` is the maximum of that attributed **sum** over ticks in the lane window (not the max of any single PID's pages). PIDs mapped to other lanes do not contribute.

## Journal kinds

Durable journal lines under `/app/output/scratch/hwm.jnl` use JSON objects whose `kind` field is one of:

- `sample` — residency tick (`pid`, `pages`, `lane`)
- `fence` — closes a lane window (`lane`, optional `gen`)
- `roster` — patches membership mid-window (`patch` map of pid string to lane id)

Single-letter legacy kinds are not part of the current contract.

## Roster schedules

Roster schedules live under `/app/environment/fixtures/roster/<slice>.json` with:

- `after`: 0-based sample index
- `patch`: map of pid string to destination lane id

The patch is applied **before** the sample at index `after` is attributed. Immediately after the patch, live residency entries that no longer map to the active lane must be dropped and must not contribute to later attributed sums. Historical high-water already recorded for the window must not be recomputed downward.

When the driver journals the stream, the `roster` record must appear before the `sample` record for that same index so journal reconstruct matches the live path.

## Fence and reload isolation

Fence records close a lane window for journal reconstruct. Reload handoff between slices must enforce the same isolation:

- prior-lane live residency must not carry into the next lane
- prior-lane high-water must not carry into the next lane
- sticky handoff holders must be cleared across the boundary

## Checkpoint hints

The driver may write `/app/output/scratch/hwm.ckpt` as a crash-recovery hint. When a full journal reconstruct is available, graded `mended` peaks must be exactly the woven journal values. Checkpoint tallies must never override a complete journal reconstruction, regardless of checkpoint generation, including raw unattributed page sums stored as hints.

## Coverage and invariants

- `oak`, `pine`, `ash` appear in `clean`, `mended`, and `reloaded`
- `elm` appears in `clean` and `mended` only
- For each of `oak`/`pine`/`ash`/`elm`, `mended` `peak_pages` must equal `clean` `peak_pages`
- After a lane handoff on `reloaded`, the next lane's `peak_pages` must equal that lane's `clean` value (no sticky prior high-water)
- Every graded row must satisfy `peak_pages <= budget_cap`

## Fixtures

Membership maps: `/app/environment/fixtures/members/map_a.json` (default), `/app/environment/fixtures/members/map_b.json` (wide arm).
Sample streams: `/app/environment/fixtures/samples/r1.jsonl` .. `/app/environment/fixtures/samples/r4.jsonl`.
Roster schedules: `/app/environment/fixtures/roster/<slice>.json`.
The driver regenerates the graded report from these inputs plus journal reconstruct. Hand-edited JSON is not sufficient.
