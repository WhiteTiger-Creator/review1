# Numeric format specifications

Supported quantized dtypes in variant packs: int8.

INT8 dequantization: value_fp = (stored - zero_point) * scale.

Quantization uncertainty half-width for each stored int8 weight or bias term: scale divided by 2.

When a variant omits quant override for an affine layer, use reference float w and b for both ref and quant paths with zero quant error on the quant path.

Drift bound comparison uses measured_drift less than or equal to drift_bound for pass. Strict less-than only applies to epoch annex tightening described in /app/docs/certification-epoch-policy.md.
