# Layer-order digest seal

After walk-intervals writes layer-intervals.json, the tool must write walk-witness.json in the same interval-store directory.

walk-witness.json schema:

- layer_order_digest: lowercase hex sha256 of UTF-8 bytes formed by concatenating layer_id strings in topological walk order exactly as stored in layer-intervals.json layers array. Do not sort layer ids alphabetically.

publish-report must read walk-witness.json, recompute the digest from the loaded snapshot layer order, and refuse publish when digests differ.

On successful publish, bump /app/var/qbound-cert-ledger/publish-seq.json for the graph_id with monotonic publish_seq and the layer_order_digest used.
