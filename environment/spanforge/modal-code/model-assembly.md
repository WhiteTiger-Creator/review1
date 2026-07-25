# Model assembly and physicality

**Normative specification.** Engineering contracts for the bridge finite-element modal baseline. Anchors `MA-1` through `MA-11` state mathematical requirements and observable outcomes only. The `spectrum` command validates these contracts and emits the baseline eigen-spectrum JSON.

## MA-1 — model schema

The model is strict UTF-8 JSON:

```json
{
  "format": "bridge-modal-model-v1",
  "dofs": ["D01", "D02"],
  "mass": [[1.0, 0.0], [0.0, 1.0]],
  "fixed_stiffness": [[2.0, -1.0], [-1.0, 2.0]],
  "groups": [
    {
      "group_id": "main-cable",
      "lower": 0.8,
      "upper": 1.2,
      "initial": 1.0,
      "reference": 1.0,
      "contribution": [[0.2, 0.0], [0.0, 0.2]]
    }
  ]
}
```

Reject duplicate object members, unknown members, malformed UTF-8, non-finite numbers, wrong dimensions, trailing bytes, and wrong types.

There are 2–24 DOFs and 1–8 stiffness groups.

DOF identifiers and group identifiers contain 1–48 ASCII letters, digits, dots, underscores, or hyphens and begin with a letter or digit. They are unique.

## MA-2 — matrix ordering

Matrix row and column order follows `dofs`.

Equivalent model permutations may reorder DOFs only when every matrix row and column is remapped consistently. Equivalent group permutations may reorder whole group objects.

Canonical DOF order and canonical group order are ascending identifiers.

## MA-3 — symmetry

Mass, fixed stiffness, and every group contribution must be symmetric within:

```text
abs(a_ij - a_ji) <= 1e-12 * max(1, abs(a_ij), abs(a_ji))
```

Canonicalize a valid pair to their arithmetic mean before all calculations.

A matrix outside this tolerance is rejected rather than silently symmetrized.

## MA-4 — mass physicality

The mass matrix must be positive definite.

Use the canonicalized matrix. Rejection occurs when a Cholesky factorization encounters a nonpositive pivot under the documented absolute pivot floor `1e-14`.

No diagonal shifting or regularization is permitted.

## MA-5 — stiffness assembly

For parameter vector `theta`:

```text
K(theta) = fixed_stiffness
         + sum(theta_g * contribution_g)
```

Every group satisfies:

```text
lower <= initial <= upper
lower <= reference <= upper
```

Bounds are finite and `lower < upper`.

## MA-6 — admissible stiffness box

The assembled stiffness must be positive definite at every corner of the parameter box.

Enumerate all `2^group_count` lower/upper corners in canonical group order. Apply the same Cholesky pivot rule as MA-4.

If any corner is nonphysical, reject the model before spectrum or calibration work. This guarantees every convex interior point is admissible for the affine symmetric family.

## MA-7 — generalized eigenproblem

Solve:

```text
K(theta) * phi = lambda * M * phi
```

Transform through the Cholesky factor of `M` to a symmetric standard eigenproblem.

Retain strictly positive finite eigenvalues in ascending order. Natural frequency is:

```text
frequency_hz = sqrt(lambda) / (2 * pi)
```

Use the platform `f64` value of `pi`.

## MA-8 — mass normalization and sign

Normalize every mode so:

```text
phi^T * M * phi = 1
```

For an isolated nonclustered mode, choose sign so the first component whose absolute value exceeds `1e-14` is positive.

Sign is not physically meaningful and must never change MAC or objective values.

## MA-9 — eigenvalue clusters

Consecutive eigenvalues belong to one predicted cluster when:

```text
abs(lambda_b - lambda_a) /
max(abs(lambda_a), abs(lambda_b), 1)
<= cluster_relative_tolerance
```

Apply the rule transitively in ascending eigenvalue order.

The cluster centroid frequency is the arithmetic mean of member frequencies.

## MA-10 — model identity

`model_sha256` is lowercase SHA-256 over canonical two-space-indented JSON with:

- DOFs sorted and matrices remapped;
- groups sorted;
- symmetric pairs replaced by their canonical means;
- shortest round-trip finite `f64` rendering;
- LF endings;
- one final newline.

Equivalent ordering produces the same digest.

## MA-11 — model errors

Stable model-side failures:

- `E_PATH`
- `E_MODEL_SCHEMA`
- `E_MATRIX_SYMMETRY`
- `E_MASS_PHYSICALITY`
- `E_STIFFNESS_BOX`
- `E_EIGENSYSTEM`

A failure writes one canonical JSON diagnostic line to stderr, no success output, and preserves any existing report.
