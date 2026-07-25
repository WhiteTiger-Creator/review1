# Isolate runtime authority across cache reuse

Harden the module execution service under `/app` while preserving `/app/bin/rt-run`, `/app/bin/rulesctl`, the documented ABI, and cache statistics.

Every run must honor only the intersection of capabilities in the module's valid signed document, the requesting tenant's active rules snapshot, and any reductions in the run request. A request cannot add authority.

Module bytes must remain bound to the requesting tenant, signed document, ABI version, rules context, request reductions, limits, and resource namespace used for execution. Cache hits, restart, document replacement, rules refresh, run order, or concurrent runs must not transfer authority between contexts.

Reusable compiled artifacts and attachment plans must be keyed so equivalent security contexts share reuse while differing contexts do not. Each run receives fresh mutable service state and fresh instruction, memory, output, and call budgets.

`/app/bin/rulesctl reload` publishes an immutable rules snapshot. Revoked capabilities are unavailable to every run that starts after a successful reload, including cache hits and restart. An active run may retain only the immutable authority snapshot captured when it started.

Signed documents must bind tenant identity, module digest, ABI version, capabilities, limits, and validity. Replacing bound fields without a valid signature is rejected.

Preserve ABI v1 compatibility and documented legacy defaults. ABI v2 omission means denial. Neither version may bypass current tenant rules, request reductions, namespaces, or metering.

Denied operations return documented errors such as `capability-denied` and `host-call-budget-exhausted`. They produce no external effect. Module-supplied paths, keys, names, and endpoints cannot escape the tenant namespace.

Store run results beneath `/output/rt-runs` and JSONL audit events in `/var/log/rt-daemon/audit.log`. Each run directory holds result.json naming tenant, module_digest, cache, effective_caps, and result. Audit lines name tenant, policy_digest, effective_caps, and cache. Results and audits report digests, ABI, cache outcome, and budgets consumed without secret environment values, file or KV contents, signing keys, or cache payloads.

Use `/app/config/clock` as authoritative time. Cache and state live under `/app/state`, tenant resources under `/data/tenants`, and rules or signed documents under `/app/config`. Unix socket requests use a 4-byte big-endian length prefix. Tenant KV stores use the `sqlite3` CLI layout under `/data/tenants`.

Modify source only in `/app`. Do not edit `/tests`, `/data`, signing material, or verifier-supplied artifacts. Do not contact external services.
