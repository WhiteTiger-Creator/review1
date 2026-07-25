# Calibration verdict and record

**Normative specification.** Engineering contracts for modal sensitivity, identifiability, confidence, and the durable calibration record. Anchors `CV-1` through `CV-10`. The `calibrate` command writes the MCR report at `--report` under these contracts.

## CV-1 — modal sensitivity matrix

At the accepted optimum, hold the accepted cluster assignment fixed.

For every measured cluster `j` and group `g`, compute the finite-difference derivative:

```text
S[j,g] =
  d ln(predicted_cluster_centroid_hz_j) / d theta_g
```

Use SC-11 steps and canonical group order.

If a perturbation changes cluster cardinality or invalidates the held pairing, reject with `E_SENSITIVITY`.

## CV-2 — sensitivity score

For group `g`:

```text
sensitivity_score_g =
  sqrt(sum_j measured_cluster_weight_j * S[j,g]^2)
```

Rank groups by descending score. Resolve exact ties by ascending group identifier.

## CV-3 — numerical rank

Form:

```text
G = S^T W S
```

where `W` is diagonal with measured cluster weights.

Compute symmetric eigenvalues of `G` in descending order. Let `largest` be the largest nonnegative eigenvalue.

The numerical rank is the count satisfying:

```text
eigenvalue > rank_tolerance * max(largest, 1)
```

No regularization term is included in this identifiability rank.

## CV-4 — active bounds

A group is `LOWER` when:

```text
abs(theta - lower) <= 1e-8 * max(1, abs(lower))
```

It is `UPPER` under the analogous rule. Otherwise it is `FREE`.

A parameter cannot be both because lower is strictly less than upper.

## CV-5 — overall confidence

Confidence is:

- `BOUND_ACTIVE` when any group is at a bound;
- otherwise `WEAK` when numerical rank is less than group count;
- otherwise `IDENTIFIABLE`.

This precedence is exact.

## CV-6 — per-group confidence

For each group:

- bound state `LOWER` or `UPPER` gives the same confidence label;
- a free group with sensitivity score `<= rank_tolerance` is `FREE_WEAK`;
- another free group is `FREE_IDENTIFIED`.

## CV-7 — report encoding

The report is canonical UTF-8 line-oriented text using one ASCII space, LF endings, and one final newline.

Finite values are decimal floating-point text that round-trips under IEEE-754 binary64 parsing. Canonicalize negative zero to `0`. Exact digit strings may differ across correct implementations; repeated runs of the same binary on the same inputs must still be byte-identical.

## CV-8 — report order

Emit exactly:

```text
MCR 1
STATUS CALIBRATED
MODEL_SHA256 <hex>
SURVEY_SHA256 <hex>
PLAN_SHA256 <hex>
OBJECTIVE <total> <modal_term> <regularization_term>
ITERATIONS <integer>
PROJECTED_GRADIENT_INF <value>
FINAL_STEP_INF <value>
NUMERICAL_RANK <rank> <group_count>
CONFIDENCE <BOUND_ACTIVE|WEAK|IDENTIFIABLE>
```

Then one group row per canonical group:

```text
GROUP <group_id> <theta> <lower> <upper> <reference> <bound_state> <group_confidence> <sensitivity_score> <sensitivity_rank>
```

Then one paired-cluster row per measured cluster:

```text
PAIR <measured_ids_csv> <predicted_ordinals_csv> <measured_centroid_hz> <predicted_centroid_hz> <frequency_residual> <subspace_mac> <pair_cost>
```

Then:

```text
END
```

## CV-9 — successful command output

After durable report replacement, stdout is exactly one line:

```text
CALIBRATED <absolute_report_path> <model_sha256> <survey_sha256> <confidence>
```

Write no stderr.

A bound-active or weak result still returns success when SC-10 is satisfied.

## CV-10 — publication and failure

Write the complete report to a uniquely named private sibling file, flush it, synchronize it, close it, rename it atomically over the requested report, and synchronize the containing directory.

Any path, schema, matrix, eigensystem, pairing, optimization, sensitivity, or publication failure emits one canonical JSON diagnostic line to stderr, no success output, removes private material, and preserves a pre-existing report byte-for-byte.

Additional stable codes:

- `E_SURVEY_SCHEMA`
- `E_PLAN_SCHEMA`
- `E_MODAL_PAIRING`
- `E_OPTIMIZATION`
- `E_SENSITIVITY`
- `E_REPORT`
