# Fencing-Token Authorization Ledger

You are given fixed custody evidence for one protected resource guarded by
fencing tokens. Derive the correct authorization state after every evidence
row.

Implement the Go command in `/app/environment`. The verifier builds the Go
package in that directory and runs the resulting executable with exactly one
argument: the path to a UTF-8 JSON case file. The command writes its report to
standard output; there is no output file to create.

The detailed contracts are in these files and are part of the task statement:
`/app/environment/docs/input-contract.md`,
`/app/environment/docs/event-contract.md`,
`/app/environment/docs/state-contract.md`, and
`/app/environment/docs/output-contract.md`. The JSON schemas and example input
are in `/app/environment/schemas` and `/app/environment/examples`.

Input cases contain `case_id`, `nodes`, `seed`, and `events`; unknown root
fields such as `public` may be present and must be ignored. Evidence rows are
processed in array order. Each row has `type` and `time`; supported types are
`request_lease`, `write`, `crash`, `recover`, and `tick`. The ledger clock
starts at zero. Before each row, if the row `time` is greater than the current
clock, advance the clock to that `time`; a `tick` row then adds its `delta`.
Malformed JSON must exit with nonzero status. Unknown row types inside valid
JSON are unfamiliar evidence rows and must append an `"ignored"` result rather
than crashing.

Security adjudication rules:

- The approval threshold is `floor(nodes / 2) + 1`.
- Every node has an availability flag, volatile `term`, `owner`, `token`, and
  `expires_at`, durable `term`, `owner`, `token`, and `expires_at`, and a
  durable set of committed write ids. Nodes begin available, with owner `-1`
  and all other state fields zero.
- For lease and write rows, missing or empty `targets` means all nodes. Target
  lists are normalized by ignoring out-of-range node ids and deduplicating
  repeated node ids by their first occurrence.
- `request_lease` rows have `node`, `term`, `ttl`, and `targets`. The requested
  term is the row `term` unless it is zero or missing, in which case it is the
  caller's current volatile term plus one.
- A lease request is rejected when the caller is invalid or unavailable, when
  fewer than a majority of normalized targets are available, when an active
  lease held by a different owner is visible and the requested term is not
  greater than the caller node's volatile term, or when the requested term is
  lower than the caller node's volatile term.
- Fencing tokens are allocated as `max(durable token over all nodes) + 1`.
- A granted lease computes expiry as `clock + ttl`, raised to `clock + 1` if
  the ttl would not move it into the future. The grant writes term, owner,
  token, and expiry into both durable and volatile state on every available
  normalized target. The caller's volatile state is also set to the grant even
  when the caller is not in `targets`.
- `write` rows have `node`, `token`, `write_id`, `targets`, and `value`. A
  write commits only when the caller is valid and available, the caller's
  volatile owner equals the caller, the volatile token equals the row token,
  the current clock is no greater than the volatile expiry, and a majority of
  normalized targets are available with matching durable owner, token, and
  durable expiry greater than or equal to the current clock.
- A committed write id is recorded once globally and is also stored durably on
  every available normalized target and on the caller.
- `crash` marks a valid node unavailable without erasing durable state.
  `recover` marks a valid node available and reloads volatile term, owner,
  token, and `expires_at` from durable state.
- `tick`, `crash`, and `recover` produce `"ok"` results.
- Unknown row types produce `"ignored"` results with token from the row when
  present or zero otherwise, current ledger clock, and `write_id` from the row
  when present or the empty string otherwise.
- Duplicate committed `write_id` values appear only once in `committed_writes`.
- `unique_leases` is computed from active per-node volatile lease views at the
  final clock, not from a single global authorization variable.

Output requirements:

- Emit one compact JSON object followed by exactly one final newline. Do not
  pretty-print. Do not print diagnostic text to stdout or stderr on successful
  runs.
- Top-level fields must appear in this order: `case_id`, `case_seed`,
  `results`, `committed_writes`, `invariants`, `final_state`.
- `results` contains one entry for every input row in order. Each result uses
  fields in this order: `index`, `type`, `status`, `token`, `expires_at`, and
  conditionally `write_id`.
- Status values are `granted`, `rejected`, `committed`, `ok`, and `ignored`.
- Granted lease results use token equal to the granted fencing token and
  `expires_at` equal to the granted expiry. Rejected lease results use token
  zero and `expires_at` zero.
- Committed write results preserve the row token, include `write_id`, and set
  `expires_at` to the current ledger clock at commit time, not the lease
  expiry. Rejected write results preserve the row token, include `write_id`,
  and use `expires_at` zero.
- `tick`, `crash`, and `recover` results omit `write_id`; ignored-row results
  include `write_id`. Pre-dispatch invalid-node rejections include `write_id`
  using the event value when present and the empty string otherwise.
- `committed_writes` is sorted and contains each committed identifier once.
- `invariants` fields appear as `unique_leases`, `recovery_durable_ok`, then
  `fence_monotonic`.
- `final_state` fields appear as `owner`, `token`, `term`, then `expires_at`.
  It selects the first available node in ascending order whose volatile token
  is positive and volatile expiry is greater than the final clock. If there is
  no such node, owner is `-1` and the remaining values are zero.

Grading files under `/tests`, including reference cases and oracle code, are
verifier-owned inputs. Your command must not read, import, execute, or modify
`/tests` or `/logs`; derive the ledger only from the single JSON case path
passed as the command argument.
