# Trunc decimals

Workbook field `trunc_decimals` (default fixtures use 6) governs every
feature column, beta weight, prediction, MAPE, and R² value written under
`/app/state`.

Binding half-away-from-zero scale:

1. Let `p = 10 ** trunc_decimals`.
2. For `x >= 0`, compute `math.trunc(x * p + 0.5) / p`.
3. For `x < 0`, compute `math.trunc(x * p - 0.5) / p`.

This is not floor-toward-negative-infinity of `x` at `p`, not banker's
rounding, and not plain `math.trunc(x * p) / p` without the half nudge.
