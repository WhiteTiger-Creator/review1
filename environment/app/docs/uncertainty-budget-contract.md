# Uncertainty budget contract

Dynamic-pressure relative uncertainty (independent sensors):

\[
\frac{u_q}{q_{\infty}} = \sqrt{\Big(\frac{u_\rho}{\rho}\Big)^2 + \Big(2\frac{u_V}{V}\Big)^2}
\]

Absolute dynamic-pressure uncertainty is then `u_q_inf_pa = (u_q / q_∞) · q_∞` (relative form above, then scale by `q_∞`).

Pressure-coefficient sample uncertainty:

\[
u_{C_p} = \frac{u_p}{q_{\infty}}
\]

## Pressure-path `u_Cn` / `u_Cl_pressure` (required algorithm)

Let ordered station abscissae be `x[0] … x[N-1]` (the `x_c` values of the paired tap rows, same order used for the force integral). Let

\[
u_{\Delta C_p} = \sqrt{2}\,u_{C_p}
\]

Propagate through the trapezoidal `Cn` integral with a **segment loop**, not a per-node weight accumulation:

1. Initialize `acc = 0`.
2. For each consecutive segment `i = 0 … N-2`:
   - `w = 0.5 · (x[i+1] − x[i])`
   - Add **two** identical variance terms for that segment’s two trapezoid corners:
     `acc ← acc + (w · u_ΔCp)² + (w · u_ΔCp)²`
     (equivalently `acc ← acc + 2 · (w · u_ΔCp)²`).
3. `u_Cn = √acc`.

Do **not** form classical nodal trapezoid weights (`½Δx` at ends, `½(Δx_L+Δx_R)` interior) and RSS those once per station — that yields a different numeric `u_Cn` than this facility revision.

Report `u_Cl_pressure` by rotating `u_Cn` with the same lift transform used for coefficients, treating `u_Ca = 0` for the pressure-path budget:

\[
u_{C_L,\mathrm{pressure}} = |\cos\alpha|\,u_{C_n}
\]

(`α` in radians, same `alpha_rad` as the force path.)

## Balance and combined lift

Balance lift uncertainty:

\[
u_{C_{L,b}} = |C_{L,b}|\,\frac{u_q}{q_{\infty}}
\]

Combined lift uncertainty (RSS of independent paths):

\[
u_{C_L,\mathrm{rss}} = \sqrt{u_{C_L,\mathrm{pressure}}^2 + u_{C_{L,b}}^2}
\]

Do not arithmetically sum absolute uncertainties. Emit components in `uncertainty_budget.json` as specified in `artifact-layout.md`.
