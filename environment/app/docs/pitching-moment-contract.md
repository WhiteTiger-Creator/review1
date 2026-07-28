# Pitching moment contract

Nose-up positive. Moment reference is `xref_c` from conditions (facility campaigns use `0.25`).

\[
C_m = \int_{0}^{1}(C_{p,\ell}-C_{p,u})\,(\texttt{xref\_c} - x/c)\,d(x/c)
\]

Use the trapezoidal rule on the same paired stations as the force integration. Do not integrate about the leading edge (`xref=0`) unless `xref_c` is explicitly `0`.
