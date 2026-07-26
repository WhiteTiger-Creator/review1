The command writes one compact JSON object to standard output followed by one final newline. Top-level fields appear in this order: `case_id`, `case_seed`, `results`, `committed_writes`, `invariants`, and `final_state`. No diagnostic text may appear on standard output or standard error during successful runs.

`results` contains one entry for every input row in order. Each result uses
`index` for the zero-based source row index and includes `type`, `status`,
`token`, and `expires_at`. Grant results set `expires_at` to the granted lease
expiry. Committed write results set `expires_at` to the current ledger clock at
the moment of commit, not to the lease expiry. Rejected lease results use token
zero and `expires_at` zero. Rejected write results preserve the event `token`
and use `expires_at` zero, including stale-token, unavailable-caller, expired,
and insufficient-acknowledgement denials. `tick`, `crash`, `recover`, and ignored-event results use
the current ledger clock after that row is applied.

Expected `status` values are:
- `granted`
- `rejected`
- `committed`
- `ok`
- `ignored`

`committed_writes` is sorted and contains each committed identifier once.

`write_id` is part of every write result and equals the source event
`write_id`. It is also included on ignored-row results and on pre-dispatch
invalid-node rejections, using the event value when present and the empty string
otherwise. Ordinary granted lease, tick, crash, and recover results omit
`write_id`.

Grading files under `/tests`, including reference cases and oracle code, are
verifier-owned inputs. A submitted command must not read, import, execute, or
modify `/tests` or `/logs`; it must derive the ledger only from the single JSON
case path passed as its argument.

Within `invariants`, fields appear as `unique_leases`, `recovery_durable_ok`,
then `fence_monotonic`. Within `final_state`, fields appear as `owner`,
`token`, `term`, then `expires_at`.
