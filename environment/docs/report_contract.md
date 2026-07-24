# span_parity.json contract

The regenerated artifact is `/app/output/span_parity.json`. That `span_parity` file means the offline span-screening observation record rebuilt by `exec/kit.sh`.

## Top-level fields

- `cases` field reports an array of case objects
- `tol_class` field reports the echo of `tol_class` from `tol_policy.md`
- `tol_limit` field reports the echo of `tol_limit` from `tol_policy.md` (number)
- `react_tol_limit` field reports the echo of `react_tol_limit` from `tol_policy.md` (number)
- `lin_tol_limit` field reports the echo of `lin_tol_limit` from `tol_policy.md` (number)
- `fold_probe` field reports the latest scratch-slot bias used while building the report; a clean run must keep `fold_probe` at `0.0`

The published `tol_policy` document means `/app/environment/docs/tol_policy.md` and defines the numeric bands used below.

## Case objects

- `case_id` field reports a string matching the case file stem
- `rows` field reports an array with exactly 1 screening row per case (array length 1)

## Row fields

One row per case under the full load set (`row_id` is `"main"`). Mid-span deflection uses the complete load set; load doubling scales every force via the Go helper.

- `row_id` field reports the screening row label (`"main"`)
- `defl_coarse_mm` field reports coarse-mesh mid-span deflection in millimeters
- `defl_fine_mm` field reports fine-mesh mid-span deflection in millimeters
- `react_l_coarse_n` field reports coarse-mesh left support reaction in newtons
- `react_r_coarse_n` field reports coarse-mesh right support reaction in newtons
- `react_l_fine_n` field reports fine-mesh left support reaction in newtons
- `react_r_fine_n` field reports fine-mesh right support reaction in newtons
- `defl_residual` field reports `abs(defl_coarse_mm - defl_fine_mm)`
- `react_l_residual` field reports `abs(react_l_coarse_n - react_l_fine_n)`
- `react_r_residual` field reports `abs(react_r_coarse_n - react_r_fine_n)`
- `defl_doubled_mm` field reports coarse mid-span deflection after doubling every point-load force
- `lin_defl_ratio` field reports `defl_doubled_mm / defl_coarse_mm`
- `react_l_doubled_n` field reports coarse left reaction after load doubling
- `react_r_doubled_n` field reports coarse right reaction after load doubling

## Acceptance bands

`defl_residual` must stay at most `tol_limit`.
`react_l_residual` and `react_r_residual` must stay at most `react_tol_limit`.
`abs(lin_defl_ratio - 2.0)` must stay at most `lin_tol_limit`.
`abs(react_l_doubled_n - 2.0 * react_l_coarse_n)` and `abs(react_r_doubled_n - 2.0 * react_r_coarse_n)` must stay at most `react_tol_limit`.
Across two driver invocations, all coarse deflection and reaction fields must remain unchanged.
Coarse and fine mid-span deflections must stay strictly positive for `defl_coarse_mm`, `defl_fine_mm`, and `defl_doubled_mm`.
Long soft-span case `c_e` must report `defl_fine_mm` greater than `1.0`.

Every bundled case must satisfy the same residual, linearity, reaction-scale, and rerun checks. Off-midspan multi-load cases and load-ladder cases must keep the same bands.

Independent fine-mesh check — recomputing mid-span deflection (mm) and support reactions (N) from each case's geometry and loads with an independent analytical superposition must keep `abs(defl_fine_mm - defl_mm)` at most `tol_limit`, `abs(react_l_fine_n - react_l)` at most `react_tol_limit`, and `abs(react_r_fine_n - react_r)` at most `react_tol_limit`.

Force balance — for each case with total applied force `total` equal to the sum of `force_n` over `loads`, `abs(react_l_fine_n + react_r_fine_n - total)` must stay at most `react_tol_limit`.

After load doubling, every point-load **station** (`x_m` in the case file) must remain unchanged; only forces scale. Cases with multiple loads must keep `abs(lin_defl_ratio - 2.0)` at most `lin_tol_limit` under that station-stable discipline. For multi-load cases `c_i`, `c_l`, and `c_m`, recomputing mid-span deflection from doubled forces at the original stations must keep `abs(defl_doubled_mm - defl_mm)` at most `3.0 * tol_limit`.

Coarse support reactions must also obey force balance so `abs(react_l_coarse_n + react_r_coarse_n - total)` stays at most `react_tol_limit` for total applied force on the case.

Off-midspan single-load case `c_c` must keep unequal fine reactions with `abs(react_l_fine_n - react_r_fine_n)` greater than `react_tol_limit` while coarse-vs-fine reaction residuals stay inside `react_tol_limit`.

Dense asymmetric five-load case `c_i` must keep `defl_residual` at most `tol_limit`, both reaction residuals at most `react_tol_limit`, and `abs(react_l_fine_n - react_r_fine_n)` greater than `react_tol_limit`.

Near-support load-pair case `c_j` must keep residuals inside published bands, keep `react_l_fine_n` greater than `react_r_fine_n`, and keep `react_l_fine_n > 2.0 * react_r_fine_n`.

Mesh-contrast case `c_k` must keep `defl_residual` at most `tol_limit`, keep `defl_fine_mm` greater than `0.5`, and keep `abs(lin_defl_ratio - 2.0)` at most `lin_tol_limit`.

Stepped four-load ladder case `c_l` must keep `defl_residual` at most `tol_limit`, `abs(lin_defl_ratio - 2.0)` at most `lin_tol_limit`, and doubled reactions within `react_tol_limit` of twice the coarse reactions.

Irregular six-load long-span case `c_m` must keep `defl_residual` at most `tol_limit`, keep `abs(defl_fine_mm - defl_mm)`, `abs(react_l_fine_n - react_l)`, and `abs(react_r_fine_n - react_r)` inside published bands, and keep `abs(react_l_fine_n - react_r_fine_n)` greater than `react_tol_limit`.

Bundled case files list `loads` as the load array; each case appears once in the report with a single `"main"` row (exactly 1 row in the `rows` array).

After the report path is deleted, existence is false until the driver regenerates it. Row field names ending in `_ok`, `_valid`, `_passes`, or `_green` are forbidden (treated as false answer-key suffixes).

Case objects in the report appear in ascending `case_id` order matching sorted case filenames.
The report must include at least 13 cases from the bundled directory.
`tol_class` must equal `abs_span`.
`lin_defl_ratio` must stay greater than `1.5` on every row.
Doubled coarse reactions `react_l_doubled_n` and `react_r_doubled_n` must stay greater than `0.0`.
Emitted `defl_residual` equals `abs(defl_coarse_mm - defl_fine_mm)` such that `abs(defl_residual - abs(defl_coarse_mm - defl_fine_mm))` stays at most `1e-9`.
Emitted `react_l_residual` equals `abs(react_l_coarse_n - react_l_fine_n)` such that `abs(react_l_residual - abs(react_l_coarse_n - react_l_fine_n))` stays at most `1e-9`.
Emitted `react_r_residual` equals `abs(react_r_coarse_n - react_r_fine_n)` such that `abs(react_r_residual - abs(react_r_coarse_n - react_r_fine_n))` stays at most `1e-9`.
