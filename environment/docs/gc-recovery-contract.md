# GC and recovery contract

## Recovery stages

1. Validate on-disk evidence (manifests, blobs, snapshot indexes) without mutating catalog.
2. Reconstruct missing catalog rows only from complete snapshot chains.
3. Replay `lease.journal` from the watermark entry inclusively.
4. Emit inventory JSON.

Interrupt points (`--interrupt-after`):

- `validation` — stop after tamper scan; emit `partial` inventory.
- `catalog-stage` — stop after catalog reconciliation; emit `partial` inventory.

Resume by re-running `recover` without interruption.

## GC interrupt points

- `intent` — after recording `planned` intents only.
- `first-unlink` — after unlinking the first blob.
- `catalog-commit` — after catalog deletes, before final cleanup.

GC must respect leases replayed from the journal. A release at generation *G* must not cancel acquires at generation *G+k* for the same lease id.

## Reachability

Reachable blobs include manifest layer digests, config digests, snapshot digests across the full parent closure for each image root snapshot, and any digest protected by an active lease.
