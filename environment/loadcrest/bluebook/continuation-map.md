# Loading path and fold map

Stable labels `TRACE-01` through `TRACE-13` define the ramp deck, ramp identity, pseudo-arclength coordinates, tangent orientation, predictor-corrector, step adaptation, reactive-limit events, simultaneous switching, fold bracketing, fold refinement, voltage status, the canonical archive, and CSV publication.

## Operator contract (voltage-collapse map schema)

A successful `trace` writes one ZIP archive at the absolute `--map` path with extension `.vcm`. Entries use ZIP method `Store`, mode `0644`, timestamp `1980-01-01T00:00:00Z`, and this exact order:

```text
manifest.json
curve.csv
events.csv
critical_bus.csv
critical_branch.csv
```

`manifest.json` uses two-space indentation and this fixed member order:

```json
{
  "format": "voltage-collapse-map-v1",
  "network_sha256": "lowercase-hex",
  "ramp_sha256": "lowercase-hex",
  "status": "FOLD_FOUND",
  "critical_lambda": 0.0,
  "point_count": 0,
  "event_count": 0,
  "limiting_buses": [],
  "voltage_violation_count": 0,
  "max_power_mismatch": 0.0,
  "max_arc_residual": 0.0,
  "total_active_loss": 0.0,
  "total_reactive_loss": 0.0
}
```

CSV headers are fixed in TRACE-13. Success stdout is:

```text
FOLD_MAPPED <absolute_map_path> <critical_lambda> <network_sha256> <ramp_sha256>
```

Nonphysical voltages, unresolved reactive-limit events, and an unbracketed fold are scientific failures (`E_CONTINUATION`, `E_REACTIVE_EVENT`, or `E_FOLD` as defined with POWER-12).

## TRACE-01 — ramp deck

The loading deck is strict text:

```text
AC_RAMP 1
DEMAND <bus_id> <delta_p> <delta_q>
LIMITS <voltage_min> <voltage_max>
STEPS <initial> <minimum> <maximum>
TOLERANCES <power> <arc> <reactive_event> <fold>
ITERATIONS <base_max> <corrector_max> <point_max>
END
```

Records may occur in any order after the header and before `END`.

Exactly one `DEMAND` record is required for every non-slack bus. Directions are finite and nonnegative. At least one direction component is positive.

Voltage limits are finite, positive, and `voltage_min < voltage_max`.

Step values are finite, positive, and:

```text
minimum <= initial <= maximum
```

All tolerances are finite and strictly positive. Base and corrector iteration limits are 2–100. Point maximum is 8–600.

Reject duplicate, missing, or unknown records and any demand reference to an unknown or slack bus.

## TRACE-02 — ramp identity

Canonical demand order is ascending bus identifier. Control records use the fixed semantic order shown above.

`ramp_sha256` is lowercase SHA-256 over canonical line text with shortest round-trip finite formatting, LF endings, and one final newline.

Equivalent demand-record ordering produces the same digest.

## TRACE-03 — pseudo-arclength coordinates

Let `x` contain the current power-flow state under POWER-06 and let:

```text
z = [x, lambda]
```

Use the ordinary Euclidean norm in these coordinates.

The continuation curve satisfies:

```text
F(x,lambda) = 0
```

where `F` is the current active/reactive mismatch vector.

## TRACE-04 — tangent orientation

At the base point, solve:

```text
J_x * t_x + F_lambda * t_lambda = 0
```

with `t_lambda > 0`, then normalize `t` to unit Euclidean norm.

At every later corrected point, compute a unit tangent satisfying the same null equation and choose its sign so:

```text
dot(t_new, t_previous) > 0
```

An exact zero dot product is a continuation failure.

## TRACE-05 — predictor and corrector

For accepted point `z_k`, tangent `t_k`, and step `ds`:

```text
z_predict = z_k + ds * t_k
```

Correct by solving the augmented system:

```text
F(x,lambda) = 0
dot(t_k, z - z_predict) = 0
```

The corrected point is accepted only when:

```text
max_abs(F) <= power_tolerance
abs(dot(t_k, z - z_predict)) <= arc_tolerance
```

Voltage magnitudes and lambda must remain finite; magnitudes must stay strictly positive.

## TRACE-06 — deterministic step adaptation

Begin with the configured initial step.

For an accepted corrector:

- 1–3 iterations: next step is `min(maximum, 1.25 * current)`;
- 4–6 iterations: next step equals current;
- 7 or more iterations: next step is `max(minimum, 0.5 * current)`.

A failed corrector retries from the same accepted point with half the step. Reject when the retry step would fall below `minimum`.

Record the step used for every accepted point.

## TRACE-07 — reactive-limit event

After each corrected point, compute every unswitched PV bus reactive generation.

An upper event occurs when `Q_gen > q_max + reactive_event_tolerance`; a lower event occurs when `Q_gen < q_min - reactive_event_tolerance`.

Bracket the first crossing between the previous and current accepted points. Refine along the corrected continuation curve until the violating bus differs from its limit by at most the event tolerance.

At the event:

- set that bus generation to the exact limit;
- convert the bus permanently to PQ;
- add its voltage magnitude to state order;
- recompute a tangent in the expanded system;
- continue from the event point.

Do not restore PV status later.

## TRACE-08 — simultaneous events

When multiple PV buses reach a limit at event lambda values that differ by no more than `fold_tolerance`, treat them as one event group.

Apply all switches in ascending bus identifier order at one shared corrected point. Report one event row per bus using that order.

The result may not depend on input bus ordering.

## TRACE-09 — fold bracket

Before the fold, the oriented tangent has positive `t_lambda`.

The first adjacent corrected-point pair for which:

```text
t_lambda_left > 0
t_lambda_right <= 0
```

is the fold bracket.

Do not infer the fold from Newton failure, voltage threshold crossing, determinant magnitude alone, or a maximum sampled lambda without a tangent sign change.

## TRACE-10 — fold refinement

Refine inside the fold bracket with corrected pseudo-arclength points.

At each refinement, form the normalized secant between bracket endpoints, predict at its midpoint, and correct using a hyperplane normal to that secant.

Use the corrected point’s oriented tangent to replace the positive or nonpositive bracket side.

Stop only when both:

```text
euclidean_norm(z_right - z_left) <= fold_tolerance
abs(lambda_right - lambda_left) <= fold_tolerance
```

The critical point is the bracket endpoint with larger lambda. Resolve an exact lambda tie by the endpoint with smaller maximum power mismatch.

## TRACE-11 — voltage status and limiting buses

At the critical point:

- voltage below `voltage_min` is `LOW`;
- voltage above `voltage_max` is `HIGH`;
- equality to either limit is `WITHIN`;
- every other voltage is `WITHIN`.

`limiting_buses` is the sorted set of buses whose voltage differs from the minimum critical voltage by at most `1e-10`.

Voltage violations do not turn a scientifically converged fold into command failure.

## TRACE-12 — canonical voltage-collapse map

The output path is one ZIP archive with extension `.vcm`.

Write entries in exactly this order using ZIP method `Store`, mode `0644`, no extra fields, no comments, and timestamp `1980-01-01T00:00:00Z`:

```text
manifest.json
curve.csv
events.csv
critical_bus.csv
critical_branch.csv
```

Every text entry uses UTF-8, LF endings, and one final newline.

`manifest.json` uses fixed struct-member order:

```json
{
  "format": "voltage-collapse-map-v1",
  "network_sha256": "lowercase-hex",
  "ramp_sha256": "lowercase-hex",
  "status": "FOLD_FOUND",
  "critical_lambda": 0.0,
  "point_count": 0,
  "event_count": 0,
  "limiting_buses": [],
  "voltage_violation_count": 0,
  "max_power_mismatch": 0.0,
  "max_arc_residual": 0.0,
  "total_active_loss": 0.0,
  "total_reactive_loss": 0.0
}
```

Use two-space indentation and shortest round-trip finite numbers.

## TRACE-13 — CSV content and publication

`curve.csv` columns:

```text
index,arc_length,lambda,step_size,corrector_iterations,max_power_mismatch,arc_residual,min_voltage_bus,min_voltage_pu,tangent_lambda
```

`events.csv` columns:

```text
event_index,lambda,bus_id,limit_kind,q_limit,voltage_pu
```

`critical_bus.csv` columns:

```text
bus_id,final_type,voltage_pu,angle_deg,p_generation,q_generation,p_load,q_load,voltage_state
```

`critical_branch.csv` columns:

```text
branch_id,status,from_bus,to_bus,p_from,q_from,p_to,q_to,p_loss,q_loss
```

Rows use canonical identifiers and RFC 4180 quoting only when required. Finite numbers use shortest round-trip formatting; negative zero becomes `0`.

Build the entire ZIP in a unique private sibling file opened with exclusive creation and mode `0600`. Flush, synchronize, close, rename over the requested map, and synchronize the containing directory.

On success, stdout is:

```text
FOLD_MAPPED <absolute_map_path> <critical_lambda> <network_sha256> <ramp_sha256>
```

Write no stderr.
