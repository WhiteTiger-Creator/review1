# MAPE and R²
MAPE = mean(|y-ŷ|/max(|y|,1e-6)), R² = 1 - SS_res/SS_tot.
Promote when MAPE ≤ mape_ceiling AND R² ≥ r2_floor.

Promotion is an invariant over MAPE ceiling and R² floor — both constraints must hold.

Forecast tape (`/app/state/forecast_tape.json`, scheme `hwml.forecast/v1`)
fields: `identity`, `rows`, `mape`, `r2`, `mape_ceiling` and `r2_floor` (echoed
from the workbook as floats), and `metrics_pass`. Each tape row carries `id`,
`prediction`, `target_energy`, and `abs_pct` (the truncated per-row
|y-ŷ|/max(|y|,1e-6) term). Targets may be negative; the absolute-value guard
above governs, and truncation follows the half-away-from-zero rule for
negative values too.

When the reserved cohort is empty: `rows` is `[]`, `mape` and `r2` are both
`0.0`, and `metrics_pass` is false (an empty reserved cohort never promotes).
---

Scheme id: hwml.forecast/v1
