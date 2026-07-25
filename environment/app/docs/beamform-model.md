# Phased-array RF beamforming calibration (desk schema 8)

Normative numerical model for planar satcom aperture element calibration.

## Policy file

Live path: `/app/config/cal_policy.toml`  
Rebuild from `/app/data/desk_journal.csv` per `desk-derivation.md`.  
Fingerprint: `/app/data/sealed/production_policy.sha256` must match the live file bytes.

Required keys (unknown keys fatal), in this exact table order for serialization:

| key | type | constraints |
| --- | --- | --- |
| `schema_version` | int | must equal `8` |
| `phase_tol_rad` | float | `> 0` |
| `gain_tol_db` | float | `> 0` |
| `freq_match_eps_hz` | float | `> 0` |
| `freq_anchor` | string | `first` \| `median` \| `midmean` \| `hinge` |
| `c_mps` | float | `> 0` |
| `steer_az_deg` | float | finite |
| `steer_el_deg` | float | finite |
| `el_law` | string | `flat` \| `cos_el` |
| `norm_mode` | string | `none` \| `unit_peak` \| `unit_l2` |
| `ref_antenna_id` | string | non-empty |
| `wrap_half_open` | int | `0` or `1` |
| `wrap_compose` | string | `sum_then_wrap` \| `wrap_each_then_sum` |
| `phase_sign` | int | `-1` or `1` |
| `geo_sign` | int | `-1` or `1` |
| `amp_law` | string | `voltage` \| `power` |
| `mutual_alpha` | float | `>= 0` |
| `neighbor_radius_m` | float | `> 0` |
| `mutual_kernel` | string | `linear` \| `quadratic` \| `gaussian` |
| `couple_mask` | string | `all` \| `gain_inliers` \| `dual_inliers` |
| `taper_beta` | float | `>= 0` |
| `taper_origin` | string | `centroid` \| `ref` |
| `ref_phase_align` | int | `0` or `1` |
| `align_mode` | string | `arg_zero` \| `div_ref` |
| `outlier_mode` | string | `union` \| `union_then_cluster` |
| `cluster_metric` | string | `euclid` \| `chebyshev` |
| `cluster_phase_scale` | float | `> 0` |
| `cluster_gain_scale` | float | `> 0` |
| `rms_basis` | string | `all` \| `inliers` |
| `digest_bind` | string | `weights` \| `couple_weights` \| `taper_couple_weights` \| `schema_taper_couple_w` |
| `policy_revision` | string | non-empty |

Shipped desk constants (after journal derivation) are authoritative for the default desk run.

## Phase wrap

`wrap_half_open == 1` → map into `(-π, π]` (`-π` becomes `+π`).  
`wrap_half_open == 0` → map into `[-π, π)` (`+π` becomes `-π`).

## Frequency anchor

Let the frequency reference `f*` be:

- `first` → `freq_hz` of the first data row in file order
- `median` → median of all row `freq_hz` (even N: average of the two central values after sorting)
- `midmean` → if `N < 3`, same as `median`; otherwise drop one minimum and one maximum, then arithmetic-mean the remaining `N-2` values
- `hinge` → Tukey hinge mean: if `N < 4`, same as `median`; otherwise with 0-based sorted `s`, let `lo = s[floor((N-1)/4)]`, `hi = s[ceil(3*(N-1)/4)]` (ceil as mathematical ceiling on the real value), then `f* = 0.5*(lo+hi)`

Every row must satisfy `|freq_hz - f*| <= freq_match_eps_hz`.

## Per-element residual and amplitude

```
delta = wrap(phase_meas_rad - ref_phase_rad)
```

Amplitude law:

- `amp_law == "voltage"` → `amp_linear = 10^(-gain_err_db / 20)`
- `amp_law == "power"` → `amp_linear = 10^(-gain_err_db / 10)`

## Mutual coupling

Planar Euclidean distance: `dist(i,j) = hypot(x_i - x_j, y_i - y_j)`.
Let `R = neighbor_radius_m`.

Candidate neighbors of `i` are other elements with `dist(i,j) <= R` (inclusive).

Masking of candidate `j`:

- `couple_mask == "all"` → keep every distance-qualified candidate
- `couple_mask == "gain_inliers"` → keep only if `|gain_err_db_j| <= gain_tol_db`
- `couple_mask == "dual_inliers"` → keep only if `|gain_err_db_j| <= gain_tol_db` **and** `|delta_j| <= phase_tol_rad` where `delta_j` is that element's residual after wrap (computed for every element before coupling)

Contribution of accepted neighbor `j` with `u = dist(i,j) / R`:

- `mutual_kernel == "linear"` → add `u`
- `mutual_kernel == "quadratic"` → add `u^2`
- `mutual_kernel == "gaussian"` → add `1 - exp(-u^2)`  (note: not `exp(-u^2)` alone)

```
S_i = sum of accepted contributions
couple_i = exp(-mutual_alpha * S_i)
```

Isolated elements (`S_i = 0`) keep `couple_i = 1`.

## Spatial taper

Taper origin `(ox, oy)`:

- `centroid` → arithmetic mean of all element `(x_m, y_m)`
- `ref` → `(x_m, y_m)` of the unique `ref_antenna_id` element

```
rho_i = hypot(x_i - ox, y_i - oy) / R
taper_i = exp(-taper_beta * rho_i^2)
amp_eff_i = amp_linear_i * couple_i * taper_i
```

Reported `couple` is unchanged by taper; reported `taper` is `taper_i`.

## Steering geometry

```
k = 2π * freq_hz / c_mps
az = steer_az_deg * π / 180
el = steer_el_deg * π / 180
el_factor = (el_law == "cos_el") ? cos(el) : 1
raw_geo = -k * (x_m * sin(az) * el_factor + y_m * sin(el))
geo = geo_sign * raw_geo
```

## Weight phase composition

Let `resid = phase_sign * delta`.

- `wrap_compose == "sum_then_wrap"` → `phi_w = wrap(resid + geo)`
- `wrap_compose == "wrap_each_then_sum"` → `phi_w = wrap(resid) + wrap(geo)` (no final wrap; the sum may leave `(-π, π]`)

```
w = amp_eff * (cos(phi_w) + i * sin(phi_w))
```

## Reference phase alignment

When `ref_phase_align == 0`, skip.

When `ref_phase_align == 1`:

- `align_mode == "arg_zero"` → let `θ = arg(w_ref)`; multiply every weight by `exp(-i θ)` (magnitudes unchanged)
- `align_mode == "div_ref"` → when `|w_ref| > 0`, complex-divide every weight by `w_ref` (reference becomes exactly `1+0i`); when `|w_ref| == 0`, leave unchanged

Alignment runs **before** normalization.

## Normalization

Using magnitudes `|w| = hypot(re, im)` after alignment:

- `none` — unchanged
- `unit_peak` — divide by `max(|w|)`; if max is `0`, unchanged
- `unit_l2` — divide by `sqrt(sum(|w|^2))`; if norm is `0`, unchanged

## Outliers

Primary mark: `|delta| > phase_tol_rad` OR `|gain_err_db| > gain_tol_db` (equality does not mark).

If `outlier_mode == "union"`, stop.

If `outlier_mode == "union_then_cluster"`, one expansion pass: for each primary outlier `p`, any other element `q` becomes an outlier when all of:

1. neighborhood under `cluster_metric` with radius `R`:
   - `euclid` → `hypot(dx, dy) <= R`
   - `chebyshev` → `max(|dx|, |dy|) <= R`
2. `|delta_q| > phase_tol_rad * cluster_phase_scale`
3. `|gain_err_db_q| > gain_tol_db * cluster_gain_scale`

Expansion is not recursive beyond that single pass.

`outlier_ids` are distinct ids sorted ascending lexicographically.

## Aggregates

- `rms_basis == "all"` → `rms_phase_err_rad = sqrt(mean(delta^2))` over every element
- `rms_basis == "inliers"` → same mean but only over elements with `exceeds_tol == false`; if every element is an outlier, rms is `0`

```
max_gain_dev_db = max(|gain_err_db|)   # always over every element
```

## Reference presence

`ref_antenna_id` must appear exactly once. Missing or duplicated reference id is fatal.
