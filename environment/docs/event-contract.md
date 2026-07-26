Each evidence row has `type` and `time`.

`request_lease` also has `node`, `term`, `ttl`, and `targets`.
`write` also has `node`, `token`, `write_id`, `targets`, and `value`.
`crash` or `recover` have `node`.
`tick` has `delta`.

`targets` is an array of node identifiers and may contain duplicates or unavailable nodes.

The adjudicator emits a result object for every evidence row, including `tick`, `crash`, and `recover`.

`crash` marks a valid node unavailable but does not erase durable state. Its
volatile state remains in memory until a later valid `recover`, but unavailable
nodes do not vote, acknowledge writes, or count as active leases. `recover`
marks a valid node available and reloads volatile `term`, `owner`, `token`, and
`expires_at` from that node's durable fields.

For `request_lease`, the requested term is the row `term` unless it is zero or
missing, in which case it is the caller's current volatile term plus one. The
request is rejected when the caller is invalid or unavailable, when fewer than a
majority of normalized targets are available, when an active lease held by a
different owner is visible and the requested term is not greater than the
caller node's volatile term, or when the requested term is lower than the caller
node's volatile term. A grant uses token
`max(durable token over all nodes) + 1`, computes expiry as `clock + ttl`, and
raises expiry to `clock + 1` if the ttl would not move it into the future. The
grant writes term, owner, token, and expiry into both durable and volatile state
on every available normalized target. The caller's volatile state is also set to
the grant even when the caller was not present in the target list.

For `write`, the caller must be valid and available, its volatile owner must be
itself, its volatile token must equal the event token, and the current clock
must be no greater than its volatile expiry. A write then commits only when a
majority of normalized targets are available and have durable owner equal to the
caller, durable token equal to the event token, and durable expiry greater than
or equal to the current clock. A committed write id is recorded once globally
and is also stored durably on every available normalized target and on the
caller.
