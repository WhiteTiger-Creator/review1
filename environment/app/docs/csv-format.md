# Antenna calibration CSV format

Default input: `/app/data/sample_array.csv`.

Header names are part of the contract: matching column count alone is not enough.
Wrong names (for example `id` instead of `antenna_id`) are fatal.

## Header (exact)

```
antenna_id,x_m,y_m,freq_hz,phase_meas_rad,gain_err_db,ref_phase_rad
```

| column | rules |
| --- | --- |
| `antenna_id` | trimmed non-empty string; unique |
| `x_m`, `y_m` | finite floats |
| `freq_hz` | finite, strictly positive |
| `phase_meas_rad`, `gain_err_db`, `ref_phase_rad` | finite floats |

## Parse

- Strip trailing CR before tokenize.
- Skip blank lines and lines whose first non-whitespace char is `#`.
- Data rows have exactly 7 comma fields.
- Header row is required and must match the names above in order (after trim).
- At least one data row.
- Frequency spread uses the policy `freq_anchor` against `freq_match_eps_hz` (see beamform-model.md).
