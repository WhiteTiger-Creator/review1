# Campaign schema

Each campaign directory contains:

| File | Role |
|------|------|
| `conditions.json` | Freestream and reference geometry |
| `geometry.json` | Pressure tap stations |
| `pressures.json` | Static pressure samples |
| `balance.json` | Wind-on force/moment channels |
| `tare_runs.json` | Calibration runs |

## conditions.json

- `campaign_id` (string)
- `rho_kg_m3` (float) freestream density
- `V_mps` (float) freestream speed
- `p_inf_pa` (float) freestream static pressure
- `alpha_deg` (float) angle of attack in **degrees**
- `chord_m` (float) reference chord
- `span_m` (float) reference span
- `xref_c` (float) pitching-moment reference as chord fraction (facility default `0.25`)
- `u_rho_kg_m3`, `u_V_mps`, `u_p_pa` (float) one-sigma sensor uncertainties
- `closure_tol_Cl` (float) absolute Cl agreement tolerance
- `pitot_q_pa` (optional float) **uncorrected** pitot dynamic pressure — decoy only; never use for `q_inf`

## geometry.json

`taps`: array of `{tap_id, x_c, z_c, surface}` where `surface` is `upper` or `lower` and `x_c`/`z_c` are chord-normalized coordinates.

## pressures.json

`samples`: array of `{tap_id, p_pa}`.

## balance.json

Wind-on channels: `Fx_N`, `Fz_N`, `My_Nm` in body axes (x streamwise positive aft of model, z upward, My nose-up positive).

## tare_runs.json

`runs`: array of `{run_id, wind_on, Fx_N, Fz_N, My_Nm}`. Only `wind_on == false` rows enter tare statistics.
