# Object lifecycle

1. **Import** writes blobs, snapshot metadata, manifest JSON, and catalog rows.
2. **Acquire lease** appends to `lease.journal` and mirrors into `leases` table.
3. **GC mark** records unreachable blobs in `gc_intent` with stage `planned`.
4. **GC unlink** removes blob files and advances stage to `unlinked`.
5. **GC catalog commit** deletes catalog rows and clears intent.

Leased blobs and snapshots in an active parent closure are never collected. GC intent stages are distinct: only `catalog_removed` targets may be deleted from the catalog.
