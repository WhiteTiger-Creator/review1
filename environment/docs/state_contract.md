# State contract

Durable working state lives under `--var` (default `/app/environment/var`):

- `ledger.jsonl` — append-only journal rows
- `snapshot.json` — last committed tip seal
- `shadow.json` — present only while a soft settle has not been cleared

Soft work must not be treated as settled replay state.

## status

`status` prints JSON with `state` of `settled` or `pending`.

`settled` requires all of the following:

- `shadow.json` is absent (existence is false; no active soft quarantine)
- a durable committed tip exists on the repaired journal chain; soft rows are not the tip
- `snapshot.json` seal and tip fingerprint match that committed tip
- nest materialization (`go.mod` together with `go.sum`) matches the tip's `nest_seal`
- the `--out` probe `view_digest` matches the tip plan's view digest

Otherwise `pending`. Snapshot tampering, nest content drift, probe stub or stale content, and active soft quarantine each force `pending` until `recover` or an identical committed settle rematerializes nest and probe and clears soft quarantine.

## recover

`recover` repairs the journal, then rematerializes nest and probe from the surviving committed tip, and clears soft quarantine so `shadow.json` existence is false.

Journal repair keeps only the valid sealed committed prefix. Reading stops at the first non-JSON line. Chain validation also stops at the first row whose parent seal or plan digest does not continue the tip chain, including well-formed JSON rows that do not extend the tip. Soft rows and torn tails are discarded.

## compact

`compact` rewrites an equivalent sealed committed prefix without changing recoverable plans or tip digests. Epoch numbers on surviving committed rows are preserved across the rewrite. Soft quarantine is cleared: after `compact`, `shadow.json` existence is false.
