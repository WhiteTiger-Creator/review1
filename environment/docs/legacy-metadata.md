# Legacy metadata

Older stores may omit `leases` table rows while still carrying `lease.journal` entries ahead of the catalog watermark. Recovery must replay the journal and backfill lease mirrors.

Legacy GC intent used a single `removed` stage name; modern stores use `planned`, `unlinked`, and `catalog_removed`. Mixed-stage intent must be normalized during recovery before GC continues.

Pre-2024 manifests stored only `config_digest` in the `images.manifest_digest` column. Reconstruction matches manifest files under `manifests/` when present.
