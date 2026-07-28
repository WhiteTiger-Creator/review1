# Artifact layout

After `wtac-validate eval --campaign-dir DIR --work-dir DIR`, `DIR` (work-dir) must contain:

## lift_drag_report.json

Keys (exact): `campaign_id`, `q_inf_pa`, `alpha_deg`, `alpha_rad`, `S_ref_m2`, `Cn`, `Ca`, `Cl_pressure`, `Cd_pressure`, `Cm_pressure`, `Cl_balance`, `Cd_balance`, `Cm_balance`, `Cl_delta`, `closure_pass`, `report_seal`.

`report_seal` is the lowercase **8-hex** FNV-1a **32-bit** digest (`f"{digest:08x}"` — eight hex digits, not sixteen). Hash the UTF-8 encoding of the formatted line **plus a trailing newline** (`"\n"`):

```text
{campaign_id}|{q_inf:.8f}|{Cl_pressure:.8f}|{Cd_pressure:.8f}|{Cm_pressure:.8f}|{Cl_balance:.8f}\n
```

FNV-1a offset basis `2166136261`, prime `16777619`, 32-bit mask (`& 0xFFFFFFFF` after each multiply). Do not omit the trailing newline; do not zero-pad to 16 hex characters.

## coefficient_table.csv

Header exactly:

```text
path,Cn,Ca,Cl,Cd,Cm
```

Two data rows: `pressure` then `balance`. Balance `Cn`/`Ca` are empty strings; Cl/Cd/Cm are the balance coefficients. Values formatted with 10 decimal places except empty fields.

## calibration_summary.json

Keys: `tare_run_count`, `mean_tare_Fx_N`, `mean_tare_Fz_N`, `mean_tare_My_Nm`, `sigma_tare_Fx_N`, `sigma_tare_Fz_N`, `sigma_tare_My_Nm`, `corrected_Fx_N`, `corrected_Fz_N`, `corrected_My_Nm`.

## uncertainty_budget.json

Keys: `u_q_inf_pa`, `u_Cp`, `u_Cl_pressure`, `u_Cl_balance`, `u_Cl_rss`, `components` (array of `{name, value}` with names `dyn_pressure`, `pressure_path`, `balance_path`, `rss_combined` matching the scalar fields above where applicable: dyn_pressure→u_q_inf_pa, pressure_path→u_Cl_pressure, balance_path→u_Cl_balance, rss_combined→u_Cl_rss).
