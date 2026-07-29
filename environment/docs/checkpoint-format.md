# emsolve checkpoint format (version 3)

This document is the public format contract for the binary file that
`/app/bin/emsolve` writes with `--checkpoint <path> --checkpoint-after <N>`
and reads with `--resume <path>`. It complements
`/app/docs/solver-contract.md`, which defines the finite-element model,
canonical coefficient ordering, and residuals referenced below.

All multi-byte integers and floats are little-endian. Integers are fixed
width (`uint32`/`int32`/`uint64` as noted); floats are IEEE-754 `float64`.
Length-prefixed arrays store a count field immediately before their
elements.

## 1. Envelope layout

| # | Field | Type | Size | Notes |
| - | --- | --- | --- | --- |
| 1 | `magic` | 4 ASCII bytes | 4 | literal `EMCK` |
| 2 | `version` | `uint32` | 4 | must be `3` |
| 3 | `requested_modes` | `int32` | 4 | modes requested on the run that produced this checkpoint |
| 4 | `iterations` | `int32` | 4 | completed solver iterations at checkpoint time |
| 5 | `active_dofs` | `int32` | 4 | active DOF count on the mesh the checkpoint was created from |
| 6 | `lineage_digest` | `uint64` | 8 | digest of the canonical edge-identity array (field 8); see Section 3 |
| 7 | `edge_identity_count` | `uint32` | 4 | number of entries in field 8; equal to `active_dofs` for a well-formed checkpoint |
| 8 | `edge_identities` | `edge_identity_count` x `float64` | 8 x count | one encoded identity per active edge, stored in canonical reduced coefficient order (Section 2); `edge_identities[r]` names the physical edge owning reduced coordinate `r` |
| 9 | `ritz_value_count` | `uint32` | 4 | number of stored eigenvalue estimates |
| 10 | `ritz_values` | `ritz_value_count` x `float64` | 8 x count | eigenvalue estimates, ascending |
| 11 | `ritz_vector_count` | `uint32` | 4 | number of stored eigenvectors |
| 12 | `ritz_vectors` | see below | variable | `ritz_vector_count` records, each: a `uint32` `vector_length` followed by `vector_length` x `float64` coefficients in the same canonical edge order as field 8 |
| 13 | `cache_tag_length` | `uint32` | 4 | byte length of field 14 |
| 14 | `cache_tag` | UTF-8 bytes | `cache_tag_length` | opaque, informational only; not part of any compatibility check |
| 15 | `checksum` | `uint64` | 8 | digest over every preceding byte of the envelope (fields 1-14 inclusive); see Section 3 |

For a well-formed checkpoint, every `ritz_vector`'s `vector_length` equals
`active_dofs` (field 5) and `edge_identity_count` (field 7) also equals
`active_dofs`.

A version-3 checkpoint file is written only after a successful
`--checkpoint` / `--checkpoint-after` request completes. The file must end
exactly after field 15 (`checksum`); no trailing bytes are permitted.

Field 3 (`requested_modes`) must be positive. Field 4 (`iterations`) must
be nonnegative. Field 5 (`active_dofs`) must be positive. Field 8
(`edge_identities`) must contain one encoded identity per active edge,
stored in the same order as the canonical reduced coefficient coordinates
defined in `/app/docs/solver-contract.md` Section 3. Each identity must be
unique among the active edges of supported valid meshes and must equal the
exact geometry-derived encoding in Section 2. Identities are **not**
sorted by numeric `float64` value unless canonical coefficient order happens
to imply that ordering. Alternate finite encodings, polynomial coordinate
packings, index hashes, or other implementation-defined keys are not
accepted. For accepted task meshes the prescribed encoding produces finite
`float64` values; a checkpoint containing NaN or infinity in field 8 is
invalid and must be rejected. Field 10 (`ritz_values`) must contain
finite, strictly positive physical eigenvalue estimates sorted ascending.
Every stored Ritz vector must be finite, length `active_dofs`, and
consistent with the declared vector count. Checkpoint writers must store only
finite positive physical modes after null-space filtering; intermediate
subspace Ritz estimates that still contain gradient/null-space values must be
filtered before writing fields 10 and 12 rather than suppressing checkpoint
creation.

Failed checkpoint writes or rejected `--resume` attempts must not publish a
successful `modes` payload and must obey the non-clobbering output rule in
Section 6.

## 2. Canonical edge identity encoding

Field 8 (`edge_identities`) does **not** store arbitrary sorted floats or
any alternate finite geometry-derived key an implementation might invent.
Each active reduced edge DOF carries one `float64` identity computed by the
exact algorithm below from the edge's geometry-canonical endpoint
coordinates.

For every active reduced edge `r` (in the same order as coefficient
position `r` in `/app/docs/solver-contract.md` Section 3):

1. Let `A` and `B` be the edge's two endpoint positions in world
   coordinates. Sort the endpoints lexicographically by `(x, y, z)` so `A`
   is the lower endpoint and `B` is the higher endpoint. This is the same
   coordinate-sorted endpoint pair used to define the edge's canonical
   topology key; it does not use vertex ids, element ids, or edge ids.
2. Format each coordinate with the round-trip decimal format equivalent to
   C++ `std::setprecision(17) << std::defaultfloat` for a binary64 value.
   This matches Python `format(float(v), ".17g")` for the same binary64
   value.
3. Build the edge key string **exactly** as:

   ```
   <x0> <y0> <z0>|<x1> <y1> <z1>
   ```

   where `(x0, y0, z0)` are the formatted coordinates of `A` and
   `(x1, y1, z1)` are the formatted coordinates of `B`. There is exactly
   one ASCII space between coordinates within each endpoint, exactly one
   pipe character `|` between the two endpoints, and no leading spaces,
   trailing spaces, parentheses, commas, vertex ids, element ids, locale-
   specific decimal separators, or newline characters.
4. Compute the 64-bit FNV-1a digest over the UTF-8 bytes of that exact
   string using:
   - offset basis `14695981039346656037` (`0xcbf29ce484222325`)
   - prime `1099511628211` (`0x100000001b3`)
   - multiplication modulo `2^64`
5. Reinterpret the resulting raw unsigned 64-bit integer bits as a
   little-endian IEEE-754 `float64` value and store that `float64` as
   `edge_identities[r]`.

Store the identities in the same order as the canonical active/reduced
coefficient coordinates: `edge_identities[r]` corresponds to reduced
coordinate `r`.

This encoding is intentionally geometry-derived and vertex-id independent.
For meshes related by vertex renumbering, element reordering, or local
tetrahedron orientation changes that leave the physical cavity geometry
unchanged (Section 6 of `/app/docs/solver-contract.md`), the stored
identities recomputed on the target mesh must match exactly.

`--resume` compatibility compares these exact encoded `float64` values in
canonical coefficient order. It does not use tolerance-based coordinate
comparison, vertex-id order, or acceptance of alternate encodings that
happen to be finite and unique.

## 3. Digest algorithm

Both `lineage_digest` (field 6) and `checksum` (field 15) use FNV-1a, 64-bit
variant, over raw bytes:

```
offset basis: 14695981039346656037 (0xcbf29ce484222325)
prime:        1099511628211        (0x100000001b3)

hash = offset_basis
for each byte b in the input:
    hash = hash XOR b
    hash = (hash * prime) mod 2**64
```

- `lineage_digest` hashes the little-endian `float64` bytes of every entry
  in `edge_identities` (field 8), concatenated in the stored (canonical
  coefficient) order. It is derived entirely from the Section 2 encoding
  applied to edge geometry, not from vertex ids, so it does not change when
  a mesh is renumbered, reordered, or otherwise transformed in a way
  `/app/docs/solver-contract.md` Section 6 calls invariant, and it changes
  whenever the active edge geometry itself differs (a different cavity shape
  or a different PEC boundary structure).
- `checksum` hashes the concatenation of every byte written for fields 1
  through 14, in order, including all length prefixes. It is the last field
  in the file and is not itself included in its own input.

## 4. Compatibility rules

`--resume <path>` must accept a checkpoint only when all of the following
hold against the mesh given via `--mesh`; otherwise `/app/bin/emsolve` must
exit with a nonzero status and must not emit a `modes` payload with
`computed_modes >= 1` (see Section 6):

- `magic` equals `EMCK`.
- `version` equals `3`. Checkpoints written by any other version are
  rejected outright, not partially interpreted.
- The file contains at least as many bytes as its own declared field counts
  require (no truncation) for every fixed and variable-length section.
- `checksum` (field 15), recomputed per Section 3 over the bytes actually
  present, matches the stored value.
- `active_dofs` (field 5) equals the active DOF count recomputed for the
  target mesh.
- `edge_identity_count` (field 7) equals `active_dofs`, and every entry of
  `edge_identities` (field 8) equals the Section 2 encoding recomputed for
  the corresponding active edge on the target mesh, compared in canonical
  reduced coefficient order. This is an exact `float64` equality check, not
  a tolerance-based coordinate comparison and not vertex-id order. This is
  what allows a checkpoint created on one accepted mesh to resume correctly
  on a numbering-equivalent mesh (any transform from Section 6 of
  `/app/docs/solver-contract.md`), while still rejecting a checkpoint from a
  geometrically different cavity or from a checkpoint whose identities were
  encoded by any alternate algorithm.
- Every `ritz_vector`'s `vector_length` equals `active_dofs`.

Additional semantic requirements for a checkpoint accepted by `--resume`:

- `ritz_value_count` (field 9) must equal `ritz_vector_count` (field 11).
- Both counts must equal `requested_modes` (field 3).
- Every stored Ritz vector must already use the canonical repeated-eigenspace
  basis from `/app/docs/solver-contract.md` Section 4a.
- Stored vectors must be `M`-orthonormal after remapping to the target mesh
  (absolute tolerance `1e-8`).
- Each stored Ritz value must match the Rayleigh quotient of its corresponding
  remapped vector within relative tolerance `1e-7`.
- Resume must reject a checkpoint whose vectors are finite and correctly
  sized but fail canonical-basis, `M`-orthonormality, or Rayleigh-consistency
  validation. Rejection must happen before writing or replacing the requested
  output.
- Checkpoint writers must serialize the same canonicalized vectors used for
  the successful mode payload.
- A checkpoint created from one numbering-equivalent representation and
  remapped to another must yield the same canonical coefficient arrays as a
  clean solve on the target representation.

`cache_tag` (field 14) remains informational only.

`lineage_digest` is a fast integrity pre-check: a valid checkpoint's
`lineage_digest` always equals the digest recomputed from its own
`edge_identities` little-endian bytes, so a mismatch between the two
indicates a corrupt or hand-edited file and must be rejected the same as any
other integrity failure.

## 5. Rejection cases

A conforming implementation rejects a checkpoint (nonzero exit, no
successful `modes` payload) whenever any of these hold, in addition to the
compatibility rules above:

- Wrong or missing `magic`.
- Unsupported `version` (anything other than `3`).
- The file is truncated: it ends before any declared count's data is fully
  present, for any of fields 8, 10, 12, or 14.
- `checksum` does not match the recomputed digest of fields 1-14.
- `lineage_digest` does not match the digest recomputed from
  `edge_identities`.
- `active_dofs`, `edge_identity_count`, or any `ritz_vector`'s
  `vector_length` disagrees with the target mesh or with each other as
  required above.
- Any `edge_identities` entry is non-finite, duplicated among active edges,
  out of canonical coefficient order, or does not equal the Section 2
  encoding for the target mesh's active edges.
- `ritz_value_count`, `ritz_vector_count`, or `requested_modes` disagree with
  each other as required in Section 4.
- Stored Ritz vectors fail `M`-orthonormality or Rayleigh-consistency checks
  after remapping to the target mesh (Section 4).

## 6. Failed resume must not clobber existing output

If `--resume` names an incompatible, corrupt, or otherwise rejected
checkpoint, `/app/bin/emsolve` must exit with a nonzero status before
writing any new mode payload. If a file already exists at the `--output`
path -- for example, left over from an earlier successful run -- that file
must be left byte-for-byte unchanged: the solver must not truncate,
partially overwrite, or delete it while rejecting the checkpoint. The same
non-clobbering rule applies to any other fatal error described in
`/app/docs/solver-contract.md` Section 8.
