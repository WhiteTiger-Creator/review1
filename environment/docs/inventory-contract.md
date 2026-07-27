# Store inventory contract

Recovery writes `/output/store-inventory.json` with `schema_version = 1`.

## Top-level fields

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | integer | Must be `1` |
| `status` | string | `ok`, `rejected`, or `partial` |
| `store_generation` | integer | Monotonic store generation from catalog |
| `images` | array | Sorted by `name` ascending |
| `blobs` | array | Sorted by `digest` ascending |
| `snapshots` | array | Sorted by `id` ascending |
| `leases` | array | Sorted by `lease_id` ascending |
| `quarantine` | array | Sorted by `path` ascending |
| `gc` | object | `pending` and `reclaimed` digest arrays, each sorted |

## Image entry

```json
{"name":"demo","manifest_digest":"sha256:...","root_snapshot_id":"snap-root","runnable":true}
```

`runnable` is true only when the image manifest, config blob, layer blobs, snapshot parent closure, whiteout index, and hardlink index are all valid.

## Snapshot entry

```json
{"id":"snap-a","parent":"snap-base","digest":"sha256:...","kind":"full","reachable":true}
```

`kind` is `full` or `marker`. Marker snapshots require a complete parent closure to be accepted.

## Lease entry

```json
{"lease_id":"lease-1","digest":"sha256:...","generation":3,"active":true}
```

Active leases are replayed from `lease.journal` starting at the persisted watermark entry (inclusive).

## Rejection semantics

When evidence is tampered or irreconcilable, `status` must be `rejected`, arrays may be empty, and `quarantine` must describe the failure. The store must not be mutated — `catalog.db` and blob files must remain byte-for-byte unchanged relative to the pre-recover state.

The `recover` command itself must still exit **zero** on tamper rejection: it writes the rejected inventory report and returns success without altering durable store state. Tamper detection is reported through inventory `status`, not through a non-zero CLI exit code.

The blob listing recorded in `catalog.db` is authoritative and must be validated against store evidence before conflicting on-disk metadata is trusted and before any catalog or blob mutation occurs. Blobs already recorded in `gc_intent` at `unlinked` or `catalog_removed` may have missing on-disk files without triggering tamper rejection.

## Idempotency

Running `recover` twice on a consistent store, then `gc`, must produce identical inventory aside from monotonic `store_generation` bumps from explicit generation commits only.
