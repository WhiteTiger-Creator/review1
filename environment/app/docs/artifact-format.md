# Corrected weight table

Default: `/app/weights_table.csv`

## Header

```
antenna_id,x_m,y_m,freq_hz,delta_phase_rad,amp_linear,couple,taper,steer_phase_rad,w_real,w_imag,exceeds_tol
```

## Rows

- One row per input element, sorted by `antenna_id` ascending.
- `amp_linear`: from `amp_law` before coupling and before array norm.
- `couple`: mutual-coupling factor from the model.
- `taper`: spatial taper factor from the model.
- `steer_phase_rad`: composed weight phase `phi_w` after `wrap_compose` (before `cos`/`sin`).
- `w_real` / `w_imag`: final weights after align + normalize.
- `exceeds_tol`: `true` / `false`.
- Floats: `%.10f` except `freq_hz` as `%.6f`. Signed zero formats as `0.0000000000` / `0.000000`.
- Unix newlines; trailing newline after last row.
