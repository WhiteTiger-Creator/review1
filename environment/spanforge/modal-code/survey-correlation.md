# Survey correlation and objective

**Normative specification.** Engineering contracts for ambient-vibration survey correlation, cluster pairing, and the bounded modal objective. Anchors `SC-1` through `SC-12`. The `calibrate` command applies these contracts to `--survey` and `--plan` inputs.

## SC-1 — survey schema

The survey is strict JSON:

```json
{
  "format": "bridge-modal-survey-v1",
  "sensors": ["D01", "D02"],
  "modes": [
    {
      "mode_id": "M01",
      "frequency_hz": 1.25,
      "weight": 1.0,
      "shape": [0.7, null]
    }
  ]
}
```

There are 2–24 unique sensors, each naming a model DOF, and 2–10 measured modes.

A shape has one entry per sensor. Each entry is finite or JSON `null`. `null` means unobserved and is never converted to zero.

Every mode has at least two finite channels. Frequency and weight are strictly positive and finite. Mode identifiers are unique.

## SC-2 — plan schema

The plan is strict JSON:

```json
{
  "format": "bridge-calibration-plan-v1",
  "mode_count": 4,
  "frequency_weight": 1.0,
  "shape_weight": 1.0,
  "regularization_weight": 0.01,
  "cluster_relative_tolerance": 0.0001,
  "pairing_frequency_gate": 0.35,
  "finite_difference_step": 0.0001,
  "gradient_tolerance": 1e-8,
  "step_tolerance": 1e-9,
  "objective_tolerance": 1e-12,
  "rank_tolerance": 1e-8,
  "max_iterations": 120
}
```

Reject unknown or duplicate members.

`mode_count` is at least the measured mode count and no greater than model DOF count. Positive tolerances and weights are finite. Regularization is nonnegative. Maximum iterations is 4–500.

## SC-3 — observed subspace

For a measured cluster, use the intersection of sensor channels that are finite in every member mode of that cluster.

At least two common observed channels are required. Missing channels do not contribute to norms, dot products, MAC, or dimension.

Project predicted modes to those sensor DOFs in survey order.

## SC-4 — measured clustering

Sort measured modes by frequency and then mode identifier.

Consecutive measured frequencies belong to one cluster under the same relative rule as MA-9, using squared angular frequencies for the comparison.

Apply transitively.

## SC-5 — cluster orthonormalization

Within the observed sensor space, orthonormalize measured cluster columns and predicted cluster columns using deterministic modified Gram-Schmidt.

For each candidate vector, remove projections in existing basis order. If its remaining norm is at most `1e-12`, discard it.

A cluster is usable only when both measured and predicted observed bases have rank equal to the cluster size. Otherwise that pairing is invalid.

## SC-6 — subspace MAC

For equal-size measured and predicted clusters with orthonormal observed bases `U` and `V`:

```text
subspace_mac = || U^T V ||_F^2 / cluster_size
```

The result is clamped only for roundoff to `[0, 1]`.

It is invariant to sign, order, or orthogonal rotation of bases within a repeated eigenspace.

## SC-7 — cluster frequency residual

For cluster centroids:

```text
frequency_residual =
  ln(predicted_centroid_hz / measured_centroid_hz)
```

A candidate pairing is forbidden when:

```text
abs(frequency_residual) > pairing_frequency_gate
```

Cluster sizes must match.

## SC-8 — global cluster assignment

Pair every measured cluster to a distinct predicted cluster using a global minimum-cost assignment.

For a candidate pair:

```text
pair_cost =
  measured_cluster_weight *
  (frequency_weight * frequency_residual^2
   + shape_weight * (1 - subspace_mac)^2)
```

`measured_cluster_weight` is the arithmetic mean of member mode weights.

Choose the complete assignment with minimum total pair cost. Resolve exact total-cost ties lexicographically by the vector of predicted cluster starting ordinals.

Greedy pairing is forbidden.

## SC-9 — regularization

For every group:

```text
scaled_offset =
  (theta_g - reference_g) / (upper_g - lower_g)
```

The regularization term is:

```text
regularization_weight * sum(scaled_offset^2)
```

The total objective is pair-cost sum plus regularization.

## SC-10 — bounded optimum

Search only the closed parameter box.

A reported optimum must satisfy all of:

- finite objective;
- valid global cluster assignment;
- projected gradient infinity norm `<= gradient_tolerance`, except coordinates active at a bound whose descent direction points outside the box;
- accepted final step infinity norm `<= step_tolerance` or accepted objective decrease `<= objective_tolerance`;
- iterations `<= max_iterations`.

The internal optimization method is not prescribed. Tests judge the bounded optimum, objective terms, pairing, and stopping budgets.

## SC-11 — deterministic finite differences

For objective gradients and later sensitivity, use the plan’s relative step:

```text
h_g = finite_difference_step * max(1, abs(theta_g))
```

Use central differences when both sides are inside bounds. At an active or near-active bound, use the inward one-sided difference with the same step or the largest available positive step when the box is narrower.

Evaluate groups in canonical identifier order.

## SC-12 — survey and plan identities

`survey_sha256` and `plan_sha256` are lowercase SHA-256 over canonical JSON.

Canonical survey order is sensor identifier with shape coordinates remapped, then measured mode frequency and mode identifier. Canonical plan member order is fixed by schema.

Equivalent ordering produces identical identities and reports.
