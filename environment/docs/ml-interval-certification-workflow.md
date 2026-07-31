# ML interval certification workflow

Operators certify static graph packs before INT8 deployment. The qbound-analyzer tool propagates feature intervals layerwise, writes interval-store snapshots, seals layer-order digests, and publishes drift_certification_report.json when envelopes stay inside scenario ceilings.

The workflow is ingest-pack then walk-intervals then publish-report. Feature matrix intervals never execute ONNX kernels. Eval focuses on bound overrun rows versus FP32 reference intervals.

Weight tensors load by arbitrary weight_key entries declared in graph.json and weights.json. Variant overrides overlay per-key quant blocks from variant.json.

External packs loaded through --graph-root may declare nonstandard weight_key names. Generic weight table parsing is required.
