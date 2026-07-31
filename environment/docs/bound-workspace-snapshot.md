# Staging snapshot

walk-intervals writes /app/var/qbound-interval-store/GRAPH_ID/layer-intervals.json after ingest-pack copied the pack under the same directory. walk-witness.json in the same directory records the layer_order_digest seal per /app/docs/walk-witness-contract.md.

Snapshot schema:

- graph_id: string
- variant_id: string
- scenario_id: string
- layers: array in topological order. Each entry:
  - layer_id: string
  - ref: object with lo and hi floats persisted with six digits after the decimal
  - quant: object with lo and hi floats persisted with six digits after the decimal
  - drift: float at this layer output boundary, persisted with six digits after the decimal

publish-report recomputes measured_drift from persisted ref and quant intervals in layer-intervals.json (not the stored drift field).

pack-context.json in the same directory records graph_id, variant_id, scenario_id, and certification_epoch copied from graph.json.
