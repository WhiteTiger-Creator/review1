# Workflow overview

ML evaluation operators score a wind-tunnel campaign batch in two stages, then publish deterministic coefficient-model eval artifacts.

Sequence:

1. Load campaign JSON inputs as the evaluation batch.
2. Run `wtac-validate feature` to materialize freestream and pressure-coefficient features into work-dir staging (`feature_batch.json` / `feature_ledger.json`).
3. Build freestream dynamic-pressure features from density and velocity (never uncorrected pitot; never pitot-blend decoy).
4. Extract pressure-coefficient features from tap static pressures into staged pairs.
5. Run `wtac-validate eval`, which consumes staged features for physics-informed coefficient model inference (trapezoidal force/moment).
6. Form force-balance label coefficients after wind-off tare batch statistics.
7. Compute eval metrics and an RSS uncertainty metric budget.
8. Emit eval artifacts named in artifact-layout.md, including report_seal binding the batch identity to predicted coefficients.

Eval pass requires pressure-path (model) and balance-path (label) lift coefficients to agree within `closure_tol_Cl`. Do not route freestream dynamic pressure through the optional uncorrected pitot field, the Prandtl–Glauert decoy helper, or the pitot-blend decoy helper.
