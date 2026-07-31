# ML bound product scope

This workspace implements a quantization drift certifier for frozen static graphs. Operators compare FP32 float intervals against INT8 variant intervals layer by layer. The qbound-analyzer CLI never loads ONNX, never allocates GPU buffers, and never samples activations.

The deliverable is drift_certification_report.json listing bound-overrun rows when measured_drift crosses scenario ceilings. Certification epoch metadata can tighten equality comparisons for deployment freeze windows.

Modules are grouped under /app/walk, /app/kernel, /app/numeric, /app/policy, /app/catalog, and /app/src for pack loading, topological interval walks, affine envelope widening, ReLU clipping rules, layer-order digest seals, and SHA256 report digests. Vendor code under /app/vendor is not on the publish hot path.

Success requires agreement with independent interval propagation for bundled linear-clean, linear-mixed, and hidden poison packs.
