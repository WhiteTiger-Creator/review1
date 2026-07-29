The LDAP replica under `/app/ldap` does not converge reliably after the consumer is restored from `/app/backups/consumer-state.tar`. Deleted and renamed entries can reappear, and restart behavior differs from a clean synchronization.

Repair the replication source code and configuration under `/app` so live provider and consumer state stay equivalent through initial synchronization, incremental adds, deletes, and renames, restore, and restart. Module and library behavior under `/app/lib` must be correct, not only the status report output. The modules under `/app/lib` are sourceable shell libraries; sourcing them must define their documented helpers without changing the caller's shell options, starting LDAP processes, exiting the caller, or printing unexpected output. `/app/bin/check-replica --report /output/replication-status.json` must regenerate `/output/replication-status.json` from live LDAP state; static or manual writes to that report are insufficient.

Use `/app/bin/start-ldap` and `/app/bin/stop-ldap` to control the provider and consumer processes. Use `/app/bin/restore-consumer` with the bundled backup archive when exercising restore. Run `/app/bin/check-replica` to compare live trees and write the status report. The provider listens on `ldap://127.0.0.1:1389` and the consumer on `ldap://127.0.0.1:2389`. Administration uses `cn=admin,dc=example,dc=com` with password `adminsecret`. Replication uses `cn=replicator,dc=example,dc=com` with password `replicsecret`. Ordinary reads use `uid=reader,ou=people,dc=example,dc=com` with password `readersecret`.

Public behavioral contracts are summarized in `/app/docs/replication-contract.md`. The sections below restate the externally tested rules.

## Primary suffix vs verifier suffix

`/app/bin/check-replica` reports and exits based on equivalence of the primary application suffix only, `BASE_DN=dc=example,dc=com`. The status report field `equivalent` is true only when provider and consumer entries under `dc=example,dc=com` are equivalent. `provider_entry_count` and `consumer_entry_count` count only subtree entries under `dc=example,dc=com`. `provider_context_csn` and `consumer_context_csn` come only from a base-scope lookup of `dc=example,dc=com`. The suffix `dc=verifier,dc=internal` still must replicate correctly, but it is a separate replicated suffix and must not be included in `check-replica` exit status, `equivalent`, entry counts, or BASE_DN CSN fields. Dedicated verifier-suffix checks may compare `dc=verifier,dc=internal` directly, but ordinary `check-replica --report ...` must not fail only because that separate suffix is still catching up.

`/app/bin/check-replica --report PATH` must compare the live provider and consumer trees under `BASE_DN` at report-generation time. It must exit non-zero and must not leave a stale success report whenever those primary trees are currently divergent. It must not treat matching `dc=verifier,dc=internal` state, matching `contextCSN` alone, or a recent successful restore as sufficient proof of primary equivalence. It must not wait for, trigger, or perform primary recovery or synchronization in order to turn a currently divergent primary tree into success; recovery belongs in `restore-consumer`, while `check-replica` only measures and reports live state. Verifier-suffix lag alone must not make ordinary `check-replica` fail, but primary-suffix lag must fail regardless of verifier-suffix state.

## Restore and recovery

`/app/bin/restore-consumer /app/backups/consumer-state.tar` must be a self-contained restore-and-recovery operation. When `restore-consumer` exits with status 0, the provider and consumer must be converged for `dc=example,dc=com` without requiring a later `/app/bin/check-replica` invocation to trigger recovery. `restore-consumer` should not return success before the restored consumer has completed the documented recovery path. `check-replica` may verify and report live state, but it must not be the only place where restore fallback, accesslog-cookie recovery, or refresh recovery is performed. `restore-consumer` must preserve the bundled backup archive byte-for-byte. A restored consumer must not resurrect stale deleted or renamed entries.

Restore reads optional `meta/context-csn` from the archive as the retained accesslog cookie. When that cookie is missing, empty, malformed, or no longer retained in provider `cn=accesslog`, recovery must fall back to a safe full refresh of primary consumer data and must not leave partially restored stale entries. When the cookie is still retained, delta replay via syncrepl/accesslog must converge without resurrecting tombstoned deletes or old DNs after renames. Invalid or unreadable archive paths must fail with non-zero exit before mutating an already synchronized consumer tree.

## Status report fields

When trees are equivalent under `dc=example,dc=com`, `equivalent` must be true. The status report must include `provider_uri`, `consumer_uri`, `provider_entry_count`, `consumer_entry_count`, `provider_context_csn`, `consumer_context_csn`, `recovery_mode`, and integer `checked_at` measured from live LDAP at report time.

`provider_entry_count` and `consumer_entry_count` must count only entries returned by a subtree LDAP search under `BASE_DN`, exactly `dc=example,dc=com`. These counts must exclude `dc=verifier,dc=internal` and `cn=accesslog`, and must not be totals across all configured LDAP suffixes.

`provider_context_csn` and `consumer_context_csn` must each be a single JSON string containing the first `contextCSN` value returned by a base-scope lookup of `dc=example,dc=com`, using the same unwrapped value format LDAP reports. These fields must not be arrays, comma-joined lists, whitespace-joined lists, or synthesized summaries.

`recovery_mode` must be exactly one of `none`, `delta`, or `refresh`. Use `none` when the status check reports an already synchronized live state without a restore fallback decision in that invocation; `delta` when the most recent successful `restore-consumer` used retained accesslog cookie replay; `refresh` when the most recent successful `restore-consumer` had to fall back to a full refresh because the retained cookie was absent or unusable. Do not use values such as `synchronized`, `complete`, `failed`, or `not_converged`.

If `check-replica` cannot reach LDAP or trees are not equivalent, it must exit non-zero and must not leave a previous successful report at the same path usable as if freshly regenerated. If the parent path of `--report` exists but is not a directory, `check-replica` must fail without truncating unrelated files.

## Accesslog, ACL, and libraries

Preserve the existing DNs, schemas, listener ports, access policy, and administration commands. The bundled backup archive must remain immutable.

`uid=reader,ou=people,dc=example,dc=com` may read ordinary primary people entries under `dc=example,dc=com`. The same reader bind must not enumerate or read `cn=accesslog`. The same reader bind must not enumerate or read the verifier suffix `dc=verifier,dc=internal`. Anonymous binds must not enumerate primary people entries or accesslog entries. The replicator account must be able to read accesslog entries needed for delta replay but must not gain write access to primary application entries beyond replication policy.

`/app/lib/accesslog-has-csn.sh` must return success only when the given CSN is present in accesslog as `entryCSN` or referenced in `reqMod`. `/app/lib/compare-trees.sh` equivalence must ignore multi-valued attribute order while still detecting added or removed values. `/app/lib/wait-sync.sh` must require normalized subtree equivalence, not matching `contextCSN` strings alone.

`/app/bin/start-ldap` and `/app/bin/stop-ldap` must be idempotent, must not spawn duplicate `slapd` processes for the same role, and must tolerate stale PID files after a process is gone. Provider and consumer server IDs must remain distinct and stable across config regeneration.
