# Legacy receipts

Legacy domain: `"DAC0\0legacy-build\0" || canonical_body_without_signature`.

Legacy receipts prove only the `build` predicate for configured legacy media types and
namespaces within the legacy epoch window. They cannot authorize package, test, release
approval, or transitive artifacts outside their subject.

Each receipt JSON object must include:

- `schema_version`
- `artifact_digest` (non-empty subject digest string)
- `builder_key_id` — the configured legacy builder identity is `legacy-builder-1`
- `build_epoch`
- `source_digest`
- `signature`

Receipts that omit `artifact_digest` or use any other `builder_key_id` are out of contract.
