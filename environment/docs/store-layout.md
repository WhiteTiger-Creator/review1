# Store layout

All durable state lives under `/var/lib/mint`:

```
/var/lib/mint/
  catalog.db
  lease.journal
  manifests/<image>.json
  blobs/sha256/<hex>
  snapshots/<id>/.rstore/
    snapshot.json
    whiteout.json
    hardlink.json
```

- `catalog.db` is authoritative for committed images, snapshot rows, blob catalog entries, GC intent, and lease mirrors.
- On-disk snapshot metadata is evidence that may rebuild missing catalog rows when the parent closure and blob chain are complete.
- `lease.journal` is append-only JSON lines terminated by a `{"op":"watermark","generation":N}` record after compaction.
