# Legacy metadata

Older stores may omit `leases` table rows while still carrying `lease.journal` entries ahead of the catalog watermark. Recovery must replay the journal and backfill lease mirrors.

## Legacy GC intent stage

Pre-2024 stores recorded GC progress with a single `removed` stage name. Modern stores use `planned`, `unlinked`, and `catalog_removed`.

During recovery, normalize every legacy `removed` intent row to **`unlinked`**, not `catalog_removed`. The legacy name meant the blob file had already been unlinked from disk; the catalog row was still pending deletion. Mapping to `catalog_removed` skips the catalog-delete step and leaves stale blob rows behind.

Mixed-stage intent must be normalized during recovery before GC continues. After normalization, `gc` treats `unlinked` intents as ready for catalog removal.

Pre-2024 manifests stored only `config_digest` in the `images.manifest_digest` column. Reconstruction matches manifest files under `manifests/` when present.
