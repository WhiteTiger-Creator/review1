# Summary report

Default: `/app/desk_summary.json`

Key order (exact):

```
schema_version
policy_revision
antenna_count
outlier_count
cluster_extra_count
rms_phase_err_rad
max_gain_dev_db
outlier_ids
cal_digest
steer_az_deg
steer_el_deg
norm_mode
ref_antenna_id
ref_phase_align
amp_law
wrap_compose
```

- `cluster_extra_count`: ids that are outliers only from the cluster expansion pass (`0` when `outlier_mode` is `union`).
- `outlier_ids`: ascending `antenna_id` order.
- `rms_phase_err_rad` / `max_gain_dev_db`: ordinary JSON numbers.
- `cal_digest`: lowercase hex SHA-256 of the digest blob below.
- Trailing newline after `}`.

## Digest bytes

UTF-8 blob:

1. Line `rev:<policy_revision>`
2. If `digest_bind == "schema_taper_couple_w"`, next line `schema:<schema_version>` (decimal integer, no padding)
3. For each element (sorted by `antenna_id`), with `%.10f` numerics:
   - `weights` → `antenna_id:W_REAL:W_IMAG`
   - `couple_weights` → `antenna_id:COUPLE:W_REAL:W_IMAG`
   - `taper_couple_weights` → `antenna_id:TAPER:COUPLE:W_REAL:W_IMAG`
   - `schema_taper_couple_w` → `antenna_id:TAPER:COUPLE:W_REAL:W_IMAG`
4. Final line `rms:RMS:maxg:MAXG` with `%.10f` aggregates

Before `%.10f`, map signed zero to `+0` so `-0.0` formats as `0.0000000000`.
Join lines with `\n` (no trailing blank line beyond the last content line).
