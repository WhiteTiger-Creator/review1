# MAPE and R²
MAPE = mean(|y-ŷ|/max(|y|,1e-6)), R² = 1 - SS_res/SS_tot.
Promote when MAPE ≤ mape_ceiling AND R² ≥ r2_floor.

Promotion is an invariant over MAPE ceiling and R² floor — both constraints must hold.
---

Scheme id: hwml.forecast/v1
