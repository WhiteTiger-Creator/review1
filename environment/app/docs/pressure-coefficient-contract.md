# Pressure coefficient contract

For each tap sample:

\[
C_p = \frac{p - p_{\infty}}{q_{\infty}}
\]

where `p` is `p_pa` from `pressures.json` and `p_inf` is `p_inf_pa`.

Pair stations by identical `x_c` (absolute difference ≤ 1e-12) with one `upper` and one `lower` tap. Discard unpaired stations. Sort surviving pairs by ascending `x_c`.
