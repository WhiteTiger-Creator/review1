# Dynamic pressure contract

Freestream dynamic pressure for all coefficient normalizations:

\[
q_{\infty} = \tfrac{1}{2}\,\rho\,V^{2}
\]

with `\rho = rho_kg_m3` and `V = V_mps` from `conditions.json`.

Forbidden substitutes:

- `pitot_q_pa` (uncorrected, includes probe recovery error)
- any compressibility-scaled dynamic pressure from `wtac_decoy_prandtl_q`

Reference area:

\[
S_{\mathrm{ref}} = c\,b = \texttt{chord\_m}\times\texttt{span\_m}
\]
