# emsolve solver contract

This document is the public behavioral contract for `/app/bin/emsolve`: the
`emsolve-mesh 1` input grammar, the finite-element model it evaluates, the
canonical shape of `/output/modes.json`, and the invariances a compliant
build must preserve. It complements `/app/docs/checkpoint-format.md`, which
covers the `--checkpoint`/`--resume` file format.

## 1. `emsolve-mesh 1` grammar and validity

```
emsolve-mesh 1
vertices <N>
<id> <x> <y> <z>            (repeated N times, one line per vertex)
elements <M>
<id> <v0> <v1> <v2> <v3>    (repeated M times, one line per tetrahedron)
boundary <K>
<id> <v0> <v1> <v2> <tag>   (repeated K times, one line per boundary face)
```

Fields are whitespace-separated tokens; the three sections (`vertices`,
`elements`, `boundary`) always appear in that order, once each.

A mesh file is valid only when all of the following hold. Any violation must
make `/app/bin/emsolve` exit with a nonzero status and must not emit a
`modes` payload with `computed_modes >= 1`:

- The header line is exactly `emsolve-mesh 1`. `1` is the only grammar
  version this contract describes.
- `N >= 4` and `M >= 1`.
- `<id>` in each section is a 0-based positional index for that section
  (`0..N-1` for vertices, `0..M-1` for elements, `0..K-1` for boundary
  faces). Every id in a section's declared range must appear exactly once;
  a repeated id or a missing id anywhere in the range is invalid.
- Every coordinate and every vertex reference is a finite number; `nan` or
  `inf` coordinates are invalid.
- A tetrahedron's four vertices must span strictly positive volume. A
  tetrahedron whose four corners are coplanar or coincident (degenerate) is
  invalid.
- Any triangular face of any tetrahedron (each tetrahedron has four) may be
  shared by at most two tetrahedra in the whole mesh. A face shared by three
  or more tetrahedra makes the mesh nonmanifold and invalid.
- Every vertex id referenced by an element (`v0..v3`) or a boundary face
  (`v0..v2`) must lie in `[0, N)`. A boundary or element record that
  references an out-of-range vertex id is invalid.
- `<tag>` must be a recognized boundary tag. `pec` (perfect electric
  conductor) is the only tag this contract defines: a `pec` face marks its
  three edges as eliminated (see Section 2). Any other tag string is not a
  supported input, and a mesh containing it is invalid.
- The file must contain exactly the records each section's declared count
  promises. A file that ends before all declared vertex, element, or
  boundary records are present, or where a record is missing one or more of
  its fields, is truncated and invalid.
- No two distinct vertex records may share identical coordinates. Duplicate
  physical vertex positions make canonical geometry-derived edge identities
  ambiguous and invalidate the mesh.
- Every `pec` boundary face must coincide with a triangular face of at
  least one tetrahedron in the `elements` section. A boundary triangle whose
  three vertices do not form a face of any listed tetrahedron is invalid.

## 2. First-order tetrahedral Nedelec (Whitney) model

### Local geometry and barycentric gradients

For a tetrahedron with corner positions `p0, p1, p2, p3` (in the local order
the element record lists them), define barycentric coordinates
`lambda_0, lambda_1, lambda_2, lambda_3` that sum to 1 on the tetrahedron
and equal 1 at the corresponding corner and 0 at the other corners. The
barycentric gradients `grad(lambda_k)` are constant vectors on each
tetrahedron.

Let `M = [p1 - p0, p2 - p0, p3 - p0]` (a 3x3 matrix whose columns are the
three edge vectors from `p0`). Then:

- `grad(lambda_1)`, `grad(lambda_2)`, and `grad(lambda_3)` are the first,
  second, and third rows of `M^{-1}`, respectively.
- `grad(lambda_0) = -(grad(lambda_1) + grad(lambda_2) + grad(lambda_3))`
  because the barycentric coordinates sum to 1 everywhere.

The signed tetrahedron volume is `det(M)`. The positive volume used in
assembly is `V = abs(det(M)) / 6`. A valid mesh requires `V > 0` on every
element.

### Local edge basis

Define six local edges by corner-index pairs:

```
local edge 0: (0, 1)   local edge 3: (1, 2)
local edge 1: (0, 2)   local edge 4: (1, 3)
local edge 2: (0, 3)   local edge 5: (2, 3)
```

For a local edge with corners `(i, j)`, the first-order Whitney/Nedelec
basis function is:

```
N_ij = lambda_i * grad(lambda_j) - lambda_j * grad(lambda_i)
```

Its curl is constant on the tetrahedron:

```
curl(N_ij) = 2 * cross(grad(lambda_i), grad(lambda_j))
```

### Local element matrices

The local stiffness (curl-curl) matrix is:

```
K_e[a, b] = V * dot(curl(N_a), curl(N_b))
```

The local mass matrix is:

```
M_e[a, b] = integral_tet dot(N_a, N_b) dV
```

For mass integration, use the 4-point degree-2 tetrahedral quadrature rule
with barycentric points:

```
alpha = (5 + 3 * sqrt(5)) / 20
beta  = (5 - sqrt(5)) / 20
```

The four quadrature points are `(alpha, beta, beta, beta)` and its three
permutations with `alpha` in each barycentric slot. Each point has weight
`1/4` (weights sum to 1). Multiply each weight by `V` to obtain the physical
quadrature weight. This rule is exact for the quadratic Nedelec mass
integrand `dot(N_a, N_b)`.

**Do not use simplified edge-vector shortcuts.** Formulas such as
`K_loc[i][j] = (e_i . e_j) / V` or local mass entries built only from edge
vectors `e_i = p_b - p_a` and `m_ij = (e_i . e_j) * V / 12` are **not**
part of this contract. They are inconsistent with the Whitney/Nedelec
curl-curl and mass operators above and do not satisfy the physical `1/s^2`
eigenvalue scaling law in Section 7.

### Global assembly

Every local edge `i` of every element resolves to one physical global edge
(identified by its two endpoint vertices) and carries a sign `s_i`: `+1`
when the element's local corner order for that edge matches the edge's
canonical orientation (Section 3), `-1` otherwise.

Global `K` and `M` are assembled by scattering `s_i * s_j * K_e[i][j]` and
`s_i * s_j * M_e[i][j]` from every element into the row/column owned by
each local edge's global identity, restricted to the active (non-PEC)
degrees of freedom described below. The same canonical map from active
global edges to coefficient positions (Section 3) must be used for every
consumer of that mapping: `K` assembly, `M` assembly, PEC elimination, the
`coefficients` written to `/output/modes.json`, residual evaluation, and
the checkpoint state in `/app/docs/checkpoint-format.md`. An
implementation where any two of those consumers disagree about which
position names which physical edge is not contract-compliant, even if each
one looks correct in isolation.

### PEC elimination and active DOFs

- A boundary face is a PEC face when its `tag` equals `pec`.
- All three edges of every PEC face are removed from the active DOF set:
  their tangential coefficient is fixed to zero, and they never appear as a
  row/column of `K` or `M` or as an entry of any mode's `coefficients`.
- `active_dofs` equals the number of distinct global mesh edges that are
  **not** touched by any PEC face. It depends only on cavity geometry and
  PEC topology, never on vertex numbering or record ordering (Section 6).

### Generalized eigenproblem and physical-mode filtering

`/app/bin/emsolve` assembles symmetric operators `K` and `M` of size
`active_dofs x active_dofs` on the reduced (non-PEC) edge space and solves
the generalized eigenproblem:

```
K x = lambda M x
```

For valid meshes, `K` is positive semidefinite and `M` is positive definite
on the active edge degrees of freedom.

The lowest-order Nedelec discretization of a closed PEC cavity contains an
exact or near-exact gradient (static) null space: fields in the span of
discrete gradients have zero or near-zero curl and therefore produce zero or
near-zero generalized eigenvalues. These are non-physical modes and must not
appear in `/output/modes.json`.

`/app/bin/emsolve` must filter this null space and report only the
requested number of **strictly positive physical cavity modes**. A candidate
eigenpair is non-physical and must be skipped when:

```
lambda <= 1e-8 * max(1, largest_abs_candidate_lambda)
```

or under an equivalent numerically stable near-zero rule with the same
intent.

After filtering:

- `modes[]` contains only the positive physical modes, sorted by ascending
  `eigenvalue`.
- `computed_modes` equals the number of modes actually written to
  `modes[]` (positive physical modes only), not the count of skipped
  gradient/null-space modes.
- Each mode's `coefficients` array has length `active_dofs` and stores `x`
  in the canonical ordering defined in Section 3.

Reported coefficient vectors should be `M`-orthonormal across the mode block:
for modes with coefficient matrix `X` (columns are mode vectors),
`X^T M X` should equal the identity matrix up to numerical tolerance.
Normalization must use the assembled mass inner product, not the Euclidean
norm.

Successful `/output/modes.json` payloads must contain only finite values.
Reported eigenvalues must be strictly positive physical modes after
null-space filtering; NaN, infinity, negative, or near-zero gradient/null-
space modes must never appear in `modes[]`.

## 3. Canonical output coefficient coordinates

Every global mesh edge is identified purely by geometry, independent of
vertex ids:

1. Let `A` and `B` be the edge's two endpoint positions. Order them so `A`
   is lexicographically smaller: compare `x` first, then `y`, then `z`
   (for a valid mesh, no two distinct vertices share identical coordinates,
   so this ordering is always well defined). This defines the edge's
   canonical orientation, used for the sign convention in Section 2.
2. The edge's canonical key is the 6-tuple
   `(A.x, A.y, A.z, B.x, B.y, B.z)`.

The active (non-PEC) global edges are assigned coefficient positions
`0 .. active_dofs - 1` in strictly ascending order of canonical key, compared
component by component left to right (lexicographic sort). This ordering
does not depend on vertex ids, the order vertices are listed in the mesh
file, the order elements are listed, the local corner order used to record
any tetrahedron, or the order or winding of boundary-face records. Two
meshes describing the same cavity geometry under any combination of those
representational choices must therefore assign the same coefficient
position to the "same" physical edge, which is what allows two runs'
`coefficients` arrays to be compared directly (subject to the sign/subspace
freedom in Section 4).

Checkpoint edge identities written to field 8 of
`/app/docs/checkpoint-format.md` use this same coordinate-sorted endpoint
pair to define each edge's geometry, but the binary checkpoint does **not**
store the coordinate tuple directly. It stores the exact encoded `float64`
identity produced by the FNV-1a and uint64-bit-reinterpretation algorithm
defined in that document's Section 2. Coefficient ordering is determined by
the canonical edge topology above; checkpoint serialization is defined only
by the checkpoint format document.

## 4. Eigenvalue ordering and cluster ids

- `modes[]` contains only positive physical modes (Section 2), sorted by
  ascending `eigenvalue`. No field other than `eigenvalue` may influence
  the sort order among modes.
- `index` is the 0-based position within `modes[]` after that sort.
- `cluster_id` groups the **reported positive physical modes** whose
  eigenvalues are numerically indistinguishable: scanning the sorted
  eigenvalues, a new cluster begins whenever the relative gap to the
  previous eigenvalue exceeds `1e-7`, where the relative gap is
  `|v_i - v_{i-1}| / max(|v_i|, |v_{i-1}|, 1.0)`.
  `cluster_id` starts at 0 and increases by 1 at each new cluster, so it is
  non-decreasing along `modes[]`.
- Within one cluster, eigenvectors span a physical eigenspace. For modes
  whose eigenvalues are distinct beyond the repeated-subgroup threshold in
  Section 4a, only deterministic sign normalization applies. For
  spectrally repeated subgroups inside one `cluster_id`, Section 4a defines
  a geometry-canonical coefficient basis that must be used for output,
  checkpoint serialization, and resume.
- `coefficients` length equals `active_dofs` for every mode.

### 4a. Canonical basis for repeated physical eigenspaces

The relative-gap `cluster_id` rule above is unchanged. Within one existing
`cluster_id`, treat a contiguous subgroup as **spectrally repeated** when

`max(abs(lambda_i - lambda_0)) <= 1e-10 * max(1, abs(lambda_0))`

where `lambda_0` is the first eigenvalue in the subgroup when scanning the
sorted modes in that cluster. Do not rotate vectors belonging to a cluster
whose eigenvalues are distinct beyond this repeated-subgroup threshold; those
vectors receive only deterministic sign normalization (step 7 below).

For a repeated subgroup containing `k` `M`-orthonormal vectors:

1. Form matrix `V`, whose columns are the subgroup vectors in canonical
   active-DOF order.
2. The projector onto the subgroup is represented through
   `project(e_r) = V * (V^T * M * e_r)` where `e_r` is canonical reduced
   coordinate `r`.
3. Scan probe coordinates `r = 0, 1, ..., active_dofs - 1`.
4. For each projected candidate:
   - perform two passes of modified Gram-Schmidt using the `M` inner product
     against already accepted canonical vectors;
   - compute its `M` norm;
   - reject it if the norm is at most `1e-12`;
   - otherwise normalize it to unit `M` norm and accept it.
5. Stop after exactly `k` independent vectors are accepted.
6. Fail clearly if fewer than `k` vectors can be constructed.
7. For every accepted vector, find the first coefficient whose absolute value
   is greater than `1e-12`; its sign must be positive. Multiply the entire
   vector by `-1` when necessary. Singleton modes and non-repeated clustered
   modes use the same first-significant-coefficient sign rule without rotating
   their eigenspaces.
8. The accepted probe order is the canonical order inside the repeated
   subgroup.
9. Recompute each emitted mode's Rayleigh quotient and diagnostics after
   canonicalization.

This construction is basis-invariant because it depends on the eigenspace
projector, the mass matrix, and canonical active-DOF coordinates, not on the
arbitrary basis returned by the eigensolver.

Representationally equivalent meshes (Section 6 transforms that preserve the
same physical coordinates: vertex-id renumbering, element-list reordering,
local tetrahedron permutation, boundary-face rotation/reversal/list reordering,
and combinations thereof) must produce matching canonical coefficient arrays
for repeated modes, not merely equivalent subspaces. Coefficient comparison
tolerances:

| Quantity | Tolerance |
| --- | --- |
| coefficient equality | absolute `1e-8` |
| `M`-orthonormality | absolute `1e-8` |
| Rayleigh consistency | relative `1e-7` |

Do not require coefficient identity under rigid translation, axis permutation,
or uniform scaling when those transformations change the geometry-derived
coordinate frame or edge identities.

## 5. Residual definitions and thresholds

Each reported physical mode carries three residuals computed from the same
assembled `K`, `M`, reported `eigenvalue`, and reported `coefficients`
vector `x` using the canonical active-edge ordering in Section 3. A compliant
run keeps every mode's residuals at or below these ceilings:

| Residual | Threshold | Definition |
| --- | --- | --- |
| `algebraic` | `<= 1e-6` | `norm(K x - lambda M x) / max(1, norm(x))`, using the reduced active-DOF operators and coefficient vector `x`. |
| `boundary_trace` | `<= 1e-8` | Root-mean-square tangential coefficient value on the eliminated PEC edges, reconstructed from `x` through the same canonical map used for `coefficients`. Because PEC edges are excluded from `x` by construction, a compliant implementation reports (very close to) 0. |
| `divergence` | `<= 1e-7` | Discrete divergence-free residual measuring orthogonality to the discrete gradient space. Let `G` be the vertex-to-active-edge gradient incidence matrix: for each active edge between free (non-PEC) vertices `v0` and `v1` in canonical orientation, row `r` has `-1` in column `v0` and `+1` in column `v1` (PEC boundary vertices carry no column). Then `divergence = norm(G^T (M x)) / max(1, norm(M x))`. Physical cavity modes are `M`-orthogonal to every discrete gradient field, so this residual is near zero for compliant results. |

The same canonical active-edge ordering must be used when assembling `K`
and `M`, when writing `coefficients`, when evaluating residuals, and when
encoding checkpoint edge identities.

Legacy subspace-angle checks (where still used) apply a principal-angle
tolerance of `0.08` radians. Repeated-subgroup coefficient payloads must
instead satisfy Section 4a elementwise on representationally equivalent
meshes.

## 6. Geometric invariances

The physical spectrum and the canonical coefficient vectors reported for a
mesh must be unchanged under each of the following representational changes,
applied individually or in any combination (Section 4a tolerances apply to
coefficient arrays):

- **Vertex renumbering**: any permutation of vertex ids, with element and
  boundary records updated to reference the new ids for the same physical
  vertices.
- **Element order**: the order tetrahedra are listed in the `elements`
  section.
- **Local tetrahedron vertex order**: any of the 24 possible local orderings
  of a single tetrahedron's four corners, chosen independently per element.
- **Boundary face order and orientation**: the order boundary faces are
  listed in the `boundary` section, and the order/winding of a face's three
  vertices (including orientation-reversing swaps, not only cyclic
  rotations).
- **Rigid translation**: adding a constant offset to every vertex position.
- **Axis permutation**: consistently relabeling which coordinate is called
  `x`, `y`, and `z`.

`active_dofs` in particular must be identical across all of the above,
since it depends only on cavity geometry and PEC topology.

## 7. Scale law

If every vertex coordinate is multiplied by a positive factor `s` (uniform
scaling, leaving angles and mesh topology unchanged), every reported
positive physical eigenvalue must scale by `1 / s^2`, while `active_dofs` and
cluster structure are preserved. Coefficient directions follow Section 4a on
meshes that remain representationally equivalent under scaling. This scaling
law follows from the
Whitney/Nedelec operators in Section 2 and is incompatible with the
removed edge-vector shortcut formulas.

## 8. Determinism, configuration, and error handling

- Given the same mesh content (up to Section 6), the same requested mode
  count, and the same configuration, `/app/bin/emsolve` must produce the
  same eigenvalues (within the `algebraic` tolerance) and the same canonical
  coefficient vectors (Section 4a) on every run, regardless of process
  working directory, environment
  variables outside the documented CLI, or which on-disk copy of the built
  solver is invoked.
- `--config <path>` names a TOML file. Recognized sections/keys are
  `[max_iterations]` key `value` (integer iteration cap), `[tolerances]`
  keys `algebraic`, `boundary_trace`, and `divergence` (floats), and
  `[solver]` key `subspace_size_factor` (integer multiplier that sizes the
  iterative search subspace relative to the requested mode count). Any key
  absent from the file keeps its built-in default, matching
  `/app/data/configs/default.toml`. Omitting `--config` uses the built-in
  defaults.
- On any fatal condition -- an invalid mesh (Section 1), an invalid or
  unsupported `--config` file, an incompatible or corrupt checkpoint
  (`/app/docs/checkpoint-format.md`), or an I/O failure -- `/app/bin/emsolve`
  must exit with a nonzero status, must not emit a `modes` payload with
  `computed_modes >= 1`, and must leave any file that already existed at the
  requested `--output` path completely unmodified: no truncation, no partial
  write, no deletion.
