# Balance cross-check contract

Correct wind-on balance channels with tare means from `tare-calibration-contract.md`:

\[
F_x' = F_x - \bar{F}_{x,\mathrm{tare}},\quad
F_z' = F_z - \bar{F}_{z,\mathrm{tare}},\quad
M_y' = M_y - \bar{M}_{y,\mathrm{tare}}
\]

Balance coefficients:

\[
C_{L,b} = \frac{F_z'}{q_{\infty} S_{\mathrm{ref}}},\quad
C_{D,b} = \frac{F_x'}{q_{\infty} S_{\mathrm{ref}}},\quad
C_{m,b} = \frac{M_y'}{q_{\infty} S_{\mathrm{ref}}\,c}
\]

Closure:

\[
|C_{L,\mathrm{pressure}} - C_{L,b}| \le \texttt{closure\_tol\_Cl}
\]

`lift_drag_report.json` must set `closure_pass` accordingly and expose `Cl_delta = Cl_pressure - Cl_balance`.
