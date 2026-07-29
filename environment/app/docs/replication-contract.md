# Replication contract

Public observable rules for `/app/bin` commands and `/app/lib` helpers.

## Primary vs verifier suffix

- `BASE_DN=dc=example,dc=com` is the primary application suffix.
- `dc=verifier,dc=internal` is an independent replicated suffix used by dedicated verifier checks.
- `/app/bin/check-replica` evaluates **only** `BASE_DN` for exit status, `equivalent`, entry counts, and context CSN fields.
- Verifier-suffix replication is still required but must not make `check-replica` fail when only the verifier suffix lags.

### Point-in-time primary comparison

- `/app/bin/check-replica --report PATH` compares the live provider and consumer trees under `BASE_DN` at report-generation time.
- It must exit non-zero and must not leave a stale success report whenever those primary trees are currently divergent.
- It must not treat matching `dc=verifier,dc=internal` state, matching `contextCSN` alone, or a recent successful restore as sufficient proof of primary equivalence.
- It must not wait for, trigger, or perform primary recovery or synchronization to turn a currently divergent primary tree into success. Recovery belongs in `restore-consumer`; `check-replica` only measures and reports live state.
- Verifier-suffix lag alone must not make ordinary `check-replica` fail. Primary-suffix lag must fail regardless of verifier-suffix state.

## Status report (`check-replica --report PATH`)

Required JSON fields:

| Field | Rule |
|-------|------|
| `provider_uri`, `consumer_uri` | Fixed listener URIs |
| `equivalent` | `true` only when provider and consumer subtrees under `BASE_DN` are equivalent |
| `provider_entry_count`, `consumer_entry_count` | Subtree counts under `BASE_DN` only; exclude `cn=accesslog` and `dc=verifier,dc=internal` |
| `provider_context_csn`, `consumer_context_csn` | Single string each: first `contextCSN` from a **base-scope** lookup of `BASE_DN` |
| `recovery_mode` | Exactly one of `none`, `delta`, `refresh` |
| `checked_at` | Integer epoch seconds from live measurement time |

`recovery_mode` meanings:

- `none` — status check on already synchronized live state without a restore decision in that invocation
- `delta` — most recent successful `restore-consumer` used retained accesslog cookie replay
- `refresh` — most recent successful `restore-consumer` fell back to full refresh because the saved cookie was missing, malformed, or no longer retained in accesslog

Reports must be computed from live LDAP at generation time, not copied from static JSON.

### Report atomicity

- When `check-replica` cannot reach LDAP or trees are not equivalent, it must exit non-zero.
- A previous successful report at the same path must not remain usable as if it were freshly regenerated.
- If the parent path of `--report` exists but is not a directory, `check-replica` must fail without truncating unrelated files.

## `restore-consumer ARCHIVE`

Self-contained restore and recovery for `BASE_DN`:

1. Validates the archive is readable tar data before mutating consumer state.
2. Reads optional `meta/context-csn` from the archive as the retained cookie.
3. When the cookie is missing, empty/whitespace-only, malformed, or not retained in provider `cn=accesslog`, perform **refresh** (safe full resync of primary consumer data) rather than partial delta replay.
4. When the cookie is retained, perform **delta** replay via syncrepl/accesslog recovery.
5. Must not resurrect deleted or renamed entries after recovery completes.
6. Must converge provider/consumer trees under `BASE_DN` before exiting 0; callers must not need a follow-up `check-replica` to trigger recovery.
7. Must not modify backup archive bytes on disk.

Sets `/app/ldap/runtime/last-recovery-mode` to `delta` or `refresh` for the most recent successful restore so a subsequent `check-replica` can emit matching `recovery_mode`.

## Accesslog and ACL

- `uid=reader,ou=people,dc=example,dc=com` may read ordinary primary people entries under `dc=example,dc=com`.
- The same reader bind must not enumerate or read `cn=accesslog`.
- The same reader bind must not enumerate or read the verifier suffix `dc=verifier,dc=internal`.
- Anonymous binds must not enumerate primary people entries or accesslog entries.
- `cn=accesslog` on the provider is readable by `cn=replicator,dc=example,dc=com` and admin, not by the reader account or anonymous binds.
- Accesslog entries for write operations must retain enough `reqDN`, `reqMod`, and `entryCSN` information for delta replay.
- `/app/lib/accesslog-has-csn.sh CSN` exits 0 when the CSN is present as `entryCSN` or referenced inside `reqMod`; otherwise exits non-zero.

## Process control

- `/app/bin/start-ldap` and `/app/bin/stop-ldap` are idempotent.
- Repeated starts must not spawn duplicate `slapd` processes for the same role.
- Stale PID files must be ignored after the process is gone.
- Provider and consumer `server-id` values must remain distinct and stable across config regeneration.

## Sourceable libraries (`/app/lib/*.sh`)

Sourcing any library must:

- define documented helpers only
- not change caller `set` options (`errexit`, `nounset`, `pipefail`, etc.)
- not start LDAP processes
- not `exit` the caller shell
- not print unexpected stdout/stderr

`/app/lib/compare-trees.sh` equivalence ignores multi-valued attribute order but still detects added or removed values.

`/app/lib/wait-sync.sh` convergence requires normalized subtree equivalence, not matching `contextCSN` strings alone.
