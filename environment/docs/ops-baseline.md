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
shortlist widget. Those choices are intentional for ops paging and must not be
confused with online serving defaults.

Per Dudík, Langford & Li (2011) appendix notes circulated internally, some teams
report unnormalized IPS on coverage dashboards; the quiet-page path mirrors
that practice when overlays roll back.
