# Quantized dtype error matrix

This matrix summarizes half-width uncertainty for bundled dtype packs. Values apply per stored coefficient in affine layers.

| dtype | half-width rule | notes |
|-------|-----------------|-------|
| int8 | scale divided by 2 per weight and per bias term | total affine uncertainty is scale when both terms quantized |
| fp32 reference | zero uncertainty | reference intervals use exact float w and b |

When variant omits quant override, quant path mirrors reference floats with zero extra width.

Drift comparisons use measured_drift from /app/docs/interval-walk-rules.md. Epoch-2 packs tighten comparisons per /app/docs/certification-epoch-policy.md.
