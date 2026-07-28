Schema-v2 gain table and replay ledger with documented SHA-256 digests.

# Published artifacts — schema v2

Two artifacts are written on success:

- `/app/output/hv_gain_table.json` — the calibration report
- `/app/state/hv_replay_ledger.json` — the replay state

Both stamp `schema_version = 2` (`SCHEMA_VERSION`). Both are UTF-8 JSON text, written
with two-space indentation and a single trailing newline, with keys in the order given
by the tables below. The files on disk are not key-sorted; key sorting applies only to
the deterministic encoding used for digests.

## Calibration report

| Order | Field | Type | Notes |
|---|---|---|---|
| 1 | `schema_version` | int | `2` |
| 2 | `profile` | string | profile name as given on the command line |
| 3 | `run_id` | int | common `run_id` of the profile's shards |
| 4 | `adc_bits` | int | common `adc_bits` of the profile's shards |
| 5 | `reference_lane` | int or null | declared reference lane, `null` on raw profiles |
| 6 | `normalized` | bool | `true` iff `reference_lane` is not `null` |
| 7 | `input_shards` | string[] | shard basenames, lexicographically sorted |
| 8 | `provenance` | object | see below |
| 9 | `lanes` | object[] | ascending `lane_id` |
| 10 | `calibration_digest` | string | lowercase hex SHA-256 |

`input_shards` is sorted lexicographically regardless of how the profile lists the
shards, and regardless of the `(shard_index, basename)` merge priority.

### `provenance`

| Order | Field | Type | Definition |
|---|---|---|---|
| 1 | `frames_read` | int | every frame decoded from every shard, before any rejection |
| 2 | `frames_rejected_duplicate` | int | frames dropped by identity deduplication |
| 3 | `frames_conflicting` | int | subset of the above whose content differed from the retained frame |
| 4 | `pedestal_frames` | int | pedestal frames that passed saturation and entered a rolling window |
| 5 | `frames_rejected_saturation` | int | frames (pedestal or pulser) touching either rail |
| 6 | `frames_rejected_coverage` | int | pulser frames whose clipped gate fell below `MIN_COVERAGE` |
| 7 | `frames_rejected_pileup` | int | pulser frames with a secondary extremum above `PILEUP_FRAC` |
| 8 | `frames_rejected_no_pedestal` | int | pulser frames with fewer than `PEDESTAL_P` pedestals available |
| 9 | `frames_rejected_noisy` | int | pulser frames whose pedestal window sigma exceeded `NOISE_SIGMA_LIMIT` |
| 10 | `frames_accepted` | int | pulser observations that entered a fit |
| 11 | `lanes_fitted` | int | lanes with status `ok` |
| 12 | `lanes_rejected` | int | lanes with any other status |

Counters are mutually exclusive apart from `frames_conflicting`, which refines
`frames_rejected_duplicate`. The following identity holds on every run:

```
frames_read - frames_rejected_duplicate
    = pedestal_frames
    + frames_accepted
    + frames_rejected_saturation
    + frames_rejected_coverage
    + frames_rejected_pileup
    + frames_rejected_no_pedestal
    + frames_rejected_noisy
```

Pedestal frames never increment `frames_accepted`, and `lanes_fitted + lanes_rejected`
equals the number of rows in `lanes`.

### Lane row

| Order | Field | Type | Notes |
|---|---|---|---|
| 1 | `lane_id` | int | |
| 2 | `status` | string | `ok`, `insufficient`, `noisy`, or `singular` |
| 3 | `n_obs` | int | accepted observations on this lane |
| 4 | `distinct_levels` | int | distinct `pulser_level` values among them |
| 5 | `pedestal_charge` | float | final rolling-window median, ADC·sample |
| 6 | `pedestal_sigma` | float | final rolling-window robust sigma |
| 7 | `gain` | float | ADC·sample per level, or the normalized ratio |
| 8 | `gain_sigma` | float | fit sigma, or the delta-method sigma |
| 9 | `intercept` | float | ADC·sample |
| 10 | `intercept_sigma` | float | |
| 11 | `drift` | float | ADC·sample per second |
| 12 | `drift_sigma` | float | |
| 13 | `t0` | float | fit reference time, seconds |
| 14 | `chi2` | float | GLS residual quadratic form |
| 15 | `dof` | int | `n_obs - 3`, or `0` when not fitted |
| 16 | `chi2_per_dof` | float or null | `null` when `dof <= 0` |
| 17 | `cond` | float | 1-norm condition number of the normal-equation matrix |

Every lane named by any merged frame gets a row, including lanes whose frames were all
rejected. Non-`ok` lanes publish `0.0` for fields 7-14 and 17, `0` for field 15, and
`null` for field 16, while fields 1-6 remain meaningful.

### Rounding

Every published float is rounded to `PUBLICATION_DIGITS = 9` decimal places using
round-half-to-even, once, after all scientific reductions — including normalization —
are complete. Rounding intermediate quantities is a contract violation. A rounded value
of `-0.0` is published as `0.0`.

Integer-typed fields are emitted as JSON integers, never as floats.

## Replay state

| Order | Field | Type | Notes |
|---|---|---|---|
| 1 | `schema_version` | int | `2` |
| 2 | `last_profile` | string | |
| 3 | `last_run_id` | int | |
| 4 | `adc_bits` | int | |
| 5 | `lane_count` | int | number of lane rows in the report |
| 6 | `lanes_fitted` | int | `ok` lanes in the report |
| 7 | `calibration_digest` | string | copied verbatim from the report |
| 8 | `replay_fingerprint` | string | lowercase hex SHA-256 |

## Deterministic encoding

Both digests hash a *documented* encoding, which is independent of the indentation used
for the files on disk. The deterministic encoding of an object is its JSON serialization
with:

- UTF-8 output bytes;
- keys sorted ascending at every level (`sort_keys=True`);
- compact separators — `,` between items and `:` between key and value, with no spaces;
- `NaN`, `Infinity`, and `-Infinity` rejected rather than emitted (`allow_nan=False`);
  a reduction that produces a non-finite published value is a bug, not a value to
  serialize;
- default ASCII escaping — every string in either artifact is ASCII, so the setting has
  no observable effect, but it must not be varied.

The digest is the lowercase hexadecimal SHA-256 of those bytes.

## Digest bindings

`calibration_digest` covers the **entire report except itself**: build the documented
encoding of the report object with the `calibration_digest` key omitted, hash it, then
store the result in that key. Every other field — provenance counters, lane rows,
`adc_bits`, `normalized`, `input_shards` — is inside the hash, so any change to any
published value changes the digest.

`replay_fingerprint` is formed the same way over the state object: deterministic encoding of
the state with the `replay_fingerprint` key omitted, hashed. It therefore binds the
state to the report through `calibration_digest`.

Both digests are computed on the rounded, published values, so a digest recomputed from
the written file always matches the stored one.

## Atomic, transactional writes

The full reduction is completed in memory before anything is written, and both artifacts
are rendered before either destination is touched. A run either writes both artifacts or
writes neither.

Each artifact is written by:

1. creating the parent directory if it does not exist;
2. writing the bytes to a temporary file in the **same** directory;
3. flushing and `fsync`-ing that file;
4. atomically renaming it onto the destination path (`os.replace`).

Readers therefore never observe a truncated or half-written artifact, and a stale
artifact left by a previous run is replaced in one step rather than being emptied first.
If the reduction raises at any point, no temporary file survives and the previous
artifacts remain exactly as they were.

## Independent verification

Reductions are compared against an independent implementation of this contract. String,
integer, boolean, and null fields — including every provenance counter, `status`,
`n_obs`, `distinct_levels`, and `dof` — must match exactly. Floating-point fields are
compared with absolute tolerances:

| Quantity | Tolerance |
|---|---|
| `gain`, `gain_sigma` | `1e-6` |
| `intercept`, `intercept_sigma`, `drift`, `drift_sigma` | `1e-6` |
| `pedestal_charge`, `pedestal_sigma` | `1e-6` |
| `t0`, `chi2`, `chi2_per_dof` | `1e-6` |
| `gain` on a normalized profile's reference lane, against `1.0` | `0` (exact) |

Digests are checked for **self-consistency and stability**, not against a reference
constant: the digest recomputed from the emitted report by the rules above must equal
the digest stored in it, the state fingerprint must likewise verify, and repeated
replays — including replays with a permuted profile shard list, and replays starting
from missing or stale output directories — must reproduce the same digest strings. Two
independent implementations that agree to the tolerances above may still differ in the
last published digit and hence in the digest, which is why digest equality across
implementations is not required.


## Verifier scratch names

Host-side pytest outside the container may use a `.verifier-run` scratch tree.
Temporary injected shards can briefly appear as `vfy_gone.pmw2`, `vfy_lockstep.pmw2`,
`vfy_negative.pmw2`, `vfy_ordering.pmw2`, `vfy_recovery.pmw2`, and `vfy_shortcut.pmw2`
under the verifier overlay only.

Provenance counters include `overstated_count` and `understated_count` when published
frame accounting is checked against observed rejections.

Shard digests for the bundled acquisitions live in
`/app/environment/fixtures/SHA256SUMS.txt`.
