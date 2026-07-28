# Eval metrics contract

Batch eval compares model predictions (pressure-path) to force-balance labels:

- Labels use wind-off-only tare means and `S_ref = chord_m * span_m`.
- Primary metric: absolute Cl residual `|Cl_model - Cl_label|` must be ≤ `closure_tol_Cl` (`closure_pass`).
- `Cl_delta` is the signed eval residual written to the batch report.
- Uncertainty metrics combine pressure-path and label-path contributions with RSS (not linear sum).
- `report_seal` binds campaign identity to the predicted coefficient payload (FNV-1a per artifact-layout.md).
