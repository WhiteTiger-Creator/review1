# CLI commands

Binary path after rebuild: /app/build/qbound-analyzer

Subcommands:

ingest-pack --graph-root PATH --graph GRAPH_ID --variant-root PATH --variant VARIANT_ID --scenario-root PATH --scenario SCENARIO_ID

Copies pack metadata into /app/var/qbound-interval-store/GRAPH_ID/ and prints QBOUND_INGEST_OK to stderr.

walk-intervals --graph GRAPH_ID

Reads staged manifest, runs interval propagation, writes layer-intervals.json, prints QBOUND_WALK_OK.

publish-report --graph GRAPH_ID

Reads snapshot, compares drifts to bound, writes /app/output/drift_certification_report.json, prints QBOUND_PUBLISH_OK.

smoke-publish runs ingest-pack, walk-intervals, and publish-report for bundled defaults used by verifier smoke only.
