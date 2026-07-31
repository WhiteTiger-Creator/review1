# Interval propagation rules

Propagation is deterministic interval arithmetic on scalar layer outputs. Each layer produces ref_interval and quant_interval after processing.

Notation: interval [lo, hi]. Drift at layer output is max(abs(ref.lo - quant.lo), abs(ref.hi - quant.hi)).

## input layer

ref_interval and quant_interval both equal scenario input_interval.

## affine layer

Reference path uses float w and b from weights.json without quantization error.

ref.lo = min(w * in_ref.lo, w * in_ref.hi) + b when w >= 0; swap lo and hi multiplicand when w < 0.
ref.hi = max(w * in_ref.lo, w * in_ref.hi) + b with same w sign rule.

Quant path uses dequantized weight w_d = (w_q - zero_point) * scale and bias b_d = (b_q - zero_point) * scale.

Per-weight quantization half-width is scale / 2. Total affine quant half-width err = scale (sum of weight and bias half-widths for scalar affine).

quant.lo = min(w_d * in_quant.lo, w_d * in_quant.hi) + b_d - err
quant.hi = max(w_d * in_quant.lo, w_d * in_quant.hi) + b_d + err

## relu layer

For either interval, lo2 = max(0, lo), hi2 = max(0, hi). If lo < 0 and hi > 0, hi2 remains hi.

## output layer

Passes through ref_interval and quant_interval unchanged. Drift is evaluated on the output layer boundary.

## Topological order

Layers must be processed in topological order so every input interval is available before a consumer runs.
