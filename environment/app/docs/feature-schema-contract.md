# Feature schema contract

Pressure-tap features for the coefficient model:

- Dynamic-pressure feature: `q_inf = 0.5 * rho * V^2` from conditions (never `pitot_q_pa`).
- Per-tap pressure-coefficient features: `Cp = (p - p_inf) / q_inf`.
- Paired upper/lower stations at identical `x_c` form the feature rows consumed by model inference.

Feature extraction must be deterministic across public and held-out batches.

Staging persistence of those features is specified in `feature-batch-contract.md`. Eval consumption of staging is specified in `eval-staging-contract.md`.
