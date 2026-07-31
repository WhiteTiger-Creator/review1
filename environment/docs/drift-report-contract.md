# Drift bound certification contract

After walk-intervals, the interval store holds layer-intervals.json under /app/var/qbound-interval-store/PACK/ where PACK is graph_id.

publish-report writes /app/output/drift_certification_report.json with:

- graph_id: string
- variant_id: string from variant pack
- scenario_id: string
- drift_bound: float from scenario
- certified: boolean, true only when violations is empty
- violations: array sorted by layer_id ascending. Each object:
  - layer_id: string
  - measured_drift: float per interval-walk-rules.md
  - bound: float copy of drift_bound
- digest: lowercase hex sha256 of a UTF-8 digest_input string built as follows.

## Digest input string (normative)

Build digest_input by concatenating fields in this exact order with no separators, spaces, or punctuation between any parts.

1. graph_id as written in the report JSON.
2. variant_id as written in the report JSON.
3. scenario_id as written in the report JSON.
4. For each entry in violations after sorting by layer_id ascending (same order as the violations array), append layer_id then measured_drift formatted with exactly six digits after the decimal point using printf-style %.6f rounding.

When violations is empty, digest_input is only graph_id + variant_id + scenario_id.

digest is lowercase hexadecimal sha256(digest_input.encode("utf-8")).

Example for graph_id linear-mixed, variant_id v-int8-loose, scenario_id scenario-standard with violations aff2 at 0.120000 and output at 0.090000 after sorting:

digest_input = linear-mixedv-int8-loosescenario-standardaff20.120000output0.090000

stderr markers:

- ingest-pack prints QBOUND_INGEST_OK on success
- walk-intervals prints QBOUND_WALK_OK on success
- publish-report prints QBOUND_PUBLISH_OK on success
