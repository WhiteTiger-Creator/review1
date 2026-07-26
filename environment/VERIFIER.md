# Verifier notes (solver-visible)

The Harbor verifier rebuilds `/app/environment` offline with
`./gradlew --offline --no-daemon clean test installDist` (equivalently
`/app/environment/gradlew --offline --no-daemon clean test installDist`),
invokes `/app/bin/lineage-audit` against shipped and generated fixtures,
validates `/output/lineage.dot` with Graphviz `dot -Tcanon`, validates
`/output/discrepancies.json` against `/app/docs/discrepancy-report-schema.json`
(including `node_count` and `edge_count`, and representation kinds
`alias_spelling` / `annotation_placement`), checks stdout summary format
`lineage-audit: reconciled N nodes, M edges`, and runs
`python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py`.

Behavioral expectations are also checked with verifier-only modules mounted at
`/tests`: `lineage_model.py`, `fixture_factory.py`, `case_library.py`, and
`test_outputs.py`. Those modules use Python's `hashlib`, `decimal`, `random`,
`json`, `re`, `subprocess`, and `tempfile` libraries. Immutable inputs are
guarded via `/tests/protected_manifest.json` entries mapping absolute paths to
`sha256` digests; protected paths must remain non-writable (`writable=false`).
Annotation tokens such as `feature_inheritance` and `warmstart` follow the
dossier and the `annotation.legacy_attrs` rules in `/app/docs/lineage-audit-cli.md`.
Unknown options such as `--bogus` are rejected per that CLI contract. The
tool version banner is `lineage-audit 1.4.2`.
