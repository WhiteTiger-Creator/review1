The adjudication maintains one state record per node. Every node has an availability
flag, volatile `term`, `owner`, `token`, and `expires_at`, durable `term`,
`owner`, `token`, and `expires_at`, and a durable set of write ids. Volatile
fields model the node's currently loaded lease view. Durable fields survive
crash and are copied back into volatile fields on recovery.

The `final_state` object contains `owner`, `token`, `term`, and `expires_at` as
integers. It selects the first available node, in ascending node order, whose
volatile token is positive and whose volatile expiry is greater than the final
clock. The selected values are that node's volatile owner, token, term, and
expiry. If no such node exists, owner is minus one and the remaining values are
zero.

The `invariants` object contains these boolean fields:
- `unique_leases`
- `recovery_durable_ok`
- `fence_monotonic`

`unique_leases` is computed from currently available nodes whose volatile token
is positive and whose volatile expiry is greater than the final clock. It is
true when there are zero or one such active volatile lease views, and false when
two or more available nodes still expose active lease views. This check is over
per-node volatile state, not a single global lease variable.

For the supplied traces, `recovery_durable_ok` and `fence_monotonic` are true
when the transition rules above are followed exactly.
