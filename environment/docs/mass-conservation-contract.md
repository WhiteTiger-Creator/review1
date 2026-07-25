# GW-Basin-12 Volumetric Mass-Conservation Contract (rev. 7)

## 1. Scope and authority

This contract governs the volumetric water-budget diagnostics emitted for basin
`GW-Basin-12`. It is normative for every quantity that appears in the emitted
document. Where an operations note, a property certificate, a mesh export field
or a source comment disagrees with this contract, this contract prevails.

The contract defines a six-stage evaluation. The stages are strictly ordered and
each stage consumes the settled output of every earlier stage:

1. Stage A — evidence admission (§3)
2. Stage B — hydraulic conductivity identification (§4)
3. Stage C — specific yield identification (§5)
4. Stage D — depth conversion and stress envelope (§6)
5. Stage E — coefficient identification by mass-balance inversion (§7)
6. Stage F — reporting-period closure and aggregation (§8, §9)

A coefficient vector is admissible only when every stage holds simultaneously.
Partial admissibility is not recognised: a vector that satisfies Stage E for the
calibration campaign but violates Stage F for a reporting period is inadmissible,
and so is a vector that closes Stage F while using property values that Stages B
and C do not support.

## 2. Evidence roots and artefacts

| Root | Content |
|---|---|
| `/app/data/mesh/` | Finite-volume cell geometry, saturated thickness, archival property metadata |
| `/app/data/aquifer_tests/` | Constant-rate pumping tests, one per mesh cell |
| `/app/data/storage_response/` | Injection / head-rise trials, one set per mesh cell |
| `/app/data/calibration/` | Calibration campaign records for Stage E |
| `/app/data/observations/` | Reporting stress periods for Stage F |

The emitted document is `/app/output/water_budget_report.json`. All evidence
under `/app/data/` is read-only input and must retain its delivered content.

Evidence file names are opaque. A file's mesh cell, campaign identifier or
period identifier is established from the fields inside the file, never from its
name, and never from the order in which the directory happens to enumerate.

## 3. Stage A — evidence admission

Two admission flags gate the evidence set, and both are load-bearing:

- Each drawdown sample in an aquifer test carries
  `in_straight_line_window`. Only samples with this flag set participate in
  Stage B. Samples outside the window are early-time readings whose curvature
  precedes the semi-logarithmic straight-line regime; admitting them biases the
  Stage B slope and therefore biases Stage E through the lateral term.
- Each calibration record carries `qualified`. Only qualified records
  participate in Stage E. An unqualified record is retained in the evidence set
  for provenance and must not enter the inversion. Admitting one makes the
  Stage E observation system inconsistent, which does not fail loudly: it
  displaces the identified pair by a small amount and surfaces only as
  non-zero Stage F residuals on the reporting periods.

Neither flag has any effect on which quantities are reported; both change the
values that are reported.

## 4. Stage B — hydraulic conductivity identification

Hydraulic conductivity is identified per mesh cell from that cell's
constant-rate pumping test by the Cooper-Jacob semi-logarithmic straight-line
method.

- The abscissa of the straight-line fit is the **decimal** logarithm of elapsed
  time. The straight-line slope is therefore a drawdown increment per decimal
  log cycle of time.
- The slope is the ordinary least-squares slope of admitted drawdown against
  that abscissa.
- Transmissivity follows from the straight-line relation
  `T = 2.303 * Q / (4 * pi * ds)` where `Q` is the constant-rate discharge of
  the test and `ds` is the per-log-cycle slope.
- Hydraulic conductivity is `K = T / sat_thickness_m` for the cell.

The factor `2.303` in the transmissivity relation is the natural-to-decimal log
bridge that the straight-line relation already carries. It is not a licence to
take the fit on a natural-logarithm abscissa: doing so rescales every identified
conductivity by that same factor, and because Stage E absorbs part of the
resulting lateral-term error into the identified pair, the corruption reaches
recharge and evapotranspiration as well as the lateral term.

`archival_k_m_per_d` in the mesh export and any conductivity figure on a
property certificate are archival records of earlier interpretations. They are
not the identified value and may not stand in for it, with or without a packing
adjustment.

## 5. Stage C — specific yield identification

Specific yield is identified per mesh cell from that cell's storage-response
trials. Each trial relates an injected volume to a head rise over the cell area
through `injected_volume_m3 = sy * area_m2 * head_rise_m`.

- The driver of the regression is `injected_volume_m3 / area_m2`; the response
  is `head_rise_m`.
- The relation is strictly proportional. The fit carries **no additive offset**:
  a zero injected volume produces a zero head rise by construction, so the
  least-squares slope is taken through the origin.
- Specific yield is the reciprocal of that slope.

Admitting an additive offset term absorbs part of the proportional signal into
the intercept and biases the slope. The bias is small in relative terms and
produces an identified specific yield that looks entirely plausible, while the
Stage F storage term it feeds is displaced by hundreds of cubic metres per
period.

`archival_sy` in the mesh export and any specific-yield figure on a property
certificate are archival records and may not stand in for the identified value.

No packing, packer-test or campaign adjustment factor may be applied to an
identified conductivity or specific yield. Identified properties enter Stages E
and F exactly as Stages B and C produce them.

## 6. Stage D — depth conversion and stress envelope

Depth fields (`precip_mm`, `pet_mm`) are millimetre depths. Conversion to metres
divides by the SI millimetre-to-metre factor: one metre is one thousand
millimetres. Any other divisor scales the recharge driver and the
evapotranspiration driver by the same wrong factor, which Stage E then partly
absorbs into the identified pair, so the error is not visible as a residual.

The evapotranspiration stress factor is

```
head_reference_m = (head_start_m + head_end_m) / 2
stress = clamp((head_reference_m - wilt_head_m) / (field_head_m - wilt_head_m), 0, 1)
```

The reference head is the **mid-period average** of the start and end heads.
Neither the start head alone nor the end head alone is the reference. The
substitution couples in two directions at once: it changes the Stage E
evapotranspiration column, and it changes the Stage F evapotranspiration term,
so the identified pair moves to compensate and the reporting residuals stay
small while every reported recharge and evapotranspiration volume is wrong. The
stress envelope heads are `wilt_head_m` and `field_head_m` as configured for
this basin.

## 7. Stage E — coefficient identification

`recharge_efficiency` and `crop_factor` are single basin-wide constants. They are
not period-specific, not cell-specific and not readable from any certificate.
They are identified by mass-balance inversion of the qualified calibration
records, using the Stage B conductivities, the Stage C specific yields, and the
Stage D conversion and stress definition.

Each qualified calibration record contributes one observation equation of the
mass-balance identity of §8 with a zero residual:

```
recharge_driver  = (precip_mm / 1000) * area_m2
et_driver        = (pet_mm / 1000) * area_m2 * stress
lateral_m3       = K * face_area_m2 * hydraulic_gradient * period_days
storage_m3       = sy * area_m2 * (head_end_m - head_start_m)

recharge_driver * recharge_efficiency
  - et_driver * crop_factor
  = pump_m3 + storage_m3 - lateral_m3
```

The pair is the least-squares solution of that two-column system over the
qualified records. Because the qualified records span differing
precipitation-to-potential-evapotranspiration ratios, the system determines the
pair uniquely.

The storage term of an observation equation is the transient elastic term. A
steady-state simplification that drops it from the inversion changes the
right-hand side of every equation whose head change is non-zero and therefore
changes the identified pair.

## 8. Stage F — reporting-period budget and closure

For every reporting stress period, with the Stage B/C properties, the Stage D
conversion and stress, and the Stage E pair:

```
recharge_m3        = (precip_mm / 1000) * area_m2 * recharge_efficiency
et_m3              = (pet_mm / 1000) * area_m2 * crop_factor * stress
lateral_m3         = K * face_area_m2 * hydraulic_gradient * period_days
storage_change_m3  = sy * area_m2 * (head_end_m - head_start_m)
balance_residual_m3 = recharge_m3 + lateral_m3 - et_m3 - pump_m3 - storage_change_m3
```

Positive `lateral_m3` is net inflow over the period. The storage term is the
full elastic term: no fractional storage scale and no steady-state
simplification may reduce or zero it for conservation reporting.

Closure is absolute and set by this contract: a period is `closure_compliant`
when `abs(balance_residual_m3) <= 1e-6`. This tolerance is a property of the
contract, not a tunable of any profile. A campaign or operational tolerance,
wherever configured, has no standing here; evaluating the closure flag against a
loose tolerance reports full compliance over residuals of arbitrary size.

`periods_compliant` must equal `period_count`, and
`max_balance_residual_m3` is the maximum **absolute** period residual.

## 9. Stage F — aggregation and ordering

Summary flux totals are strict arithmetic sums of the corresponding period
fields as emitted:

`total_recharge_m3`, `total_et_m3`, `total_lateral_m3`, `total_pump_m3`,
`total_storage_change_m3`.

No reconciliation, historian bridge, integrity pass or unit-alignment step may
alter any summary total relative to the period rows it sums. A summary total
that has been rescaled after assembly violates this contract even when every
period row is correct.

Periods are emitted as a flat array in ascending `period_id` order. Grouping by
mesh cell, by evidence file name or by any other key is not an admissible
ordering. `period_count` is the number of reporting stress periods admitted.

`calibration_source` is the absolute filesystem path of the scalar profile that
supplied the Stage D and Stage F scalars actually in force. A fallback vector
substituted for an unusable or integrity-mismatched profile is not that path,
and reporting a profile path while running a substituted vector misstates the
provenance of every number in the document.

## 10. Scalar integrity stamp

The runtime carries an embedded integrity stamp over the change-controlled
scalar vector of the profile. A stamp that does not match the loaded scalars
means the profile was altered outside change control, and the runtime then
substitutes a disconnected-kit vector whose depth divisor, stress envelope,
storage scale and mode flags are all unrelated to this contract. Scalars and
stamp are a single unit: a scalar edit that leaves the stamp stale silently
discards the edit along with every other scalar in the profile.

Deleting the profile does not neutralise this. An absent profile is treated the
same way as an integrity-mismatched one.

## 11. Emitted document schema

Top level:

```
schema_version      "1.0"
basin_id            string, the basin identifier of the evidence set
calibration_source  string, see §9
steady_state_mode   boolean
periods             array of period objects, ascending period_id
summary             object
```

Period object:

```
period_id            string
cell_id              string
period_days          number
head_start_m         number
head_end_m           number
recharge_m3          number
et_m3                number
lateral_m3           number
pump_m3              number
storage_change_m3    number
balance_residual_m3  number
et_stress            number
k_m_per_d            number, the Stage B identified conductivity of the cell
sy                   number, the Stage C identified specific yield of the cell
closure_compliant    boolean
```

Summary object:

```
period_count             number
total_recharge_m3        number
total_et_m3              number
total_lateral_m3         number
total_pump_m3            number
total_storage_change_m3  number
max_balance_residual_m3  number
periods_compliant        number
recharge_efficiency      number, the Stage E identified efficiency
crop_factor              number, the Stage E identified crop factor
```

## 12. Stage coupling summary (normative)

The stages are not independently satisfiable. The couplings below are normative
statements about the evaluation, not guidance about any particular
implementation.

| Coupling | Consequence |
|---|---|
| Stage A window flag → Stage B slope | Inadmissible samples bias every identified conductivity |
| Stage A qualified flag → Stage E pair | An inadmissible record displaces the pair and leaves Stage F residuals non-zero |
| Stage B/C properties → Stage E pair | Property error is partly absorbed by the identified pair, so residuals stay small while volumes are wrong |
| Stage D divisor → Stage E pair | A wrong divisor rescales both inversion columns and is absorbed into the pair |
| Stage D stress reference → Stages E and F | The same substitution appears on both sides and self-compensates in the residual |
| Stage E pair → Stage F volumes | Every reported recharge and evapotranspiration volume carries the identified pair |
| Stage F storage treatment → Stage E right-hand side | Dropping or scaling storage changes the identified pair as well as the reported storage |
| Stage F closure tolerance → compliance counts | A loose tolerance reports full compliance over arbitrary residuals |
| Stage F aggregation → summary totals | A post-assembly rescale breaks the summary while period rows stay correct |

Because Stage E absorbs error from Stages A through D, a small residual is not
evidence of a correct budget, and full `periods_compliant` is not evidence of an
admissible coefficient vector. Only agreement of every reported volume with the
evidence under Stages A through F establishes compliance.
