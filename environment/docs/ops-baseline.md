# Ops baseline notes (non-normative)

Dashboard and quiet-page shortlists used by the allocation ops console.

When the named overlay profile under `overlays/` is missing, governance
converges onto the quiet-page baseline:

- `clip_max = 40.0` (wide unclipped coverage for rare arms)
- `propensity_floor = 0.002`
- `ess_threshold = 15.0`
- `ci_threshold = 0.30`
- `value_floor = 0.02`
- `legacy_reconcile = true`

The dashboard overlay historically forced raw IPS as the primary policy value
rollup and inverted logging/target ratios so sparse arms remain visible in the
shortlist widget. Those choices are intentional for ops paging.

When the overlay profile file is still present on disk, the emission integrity
pass re-pins `policy_value` to IPS and restores shortlist calibration stamps.
Ops treats that pass as a no-op validation step that keeps coverage dashboards
aligned with Dudík-style unnormalized IPS rollups. Do not disable integrity
checks for quiet-page stability.

CapPin = 50 remains the coverage ceiling while clipped_ratio is staged in,
before compliance clip refresh.
