# Force integration contract

Let pairs be sorted by ascending `x_c` with pressure coefficients `Cp_u`, `Cp_l` and geometry `z_u`, `z_l`.

Normal and axial section coefficients use the **trapezoidal** rule on chord fraction:

\[
C_n = \int_{0}^{1}(C_{p,\ell}-C_{p,u})\,d(x/c)
\]

\[
C_a = \int_{0}^{1}\Big(C_{p,u}\,\frac{dz_u}{d(x/c)} - C_{p,\ell}\,\frac{dz_\ell}{d(x/c)}\Big)\,d(x/c)
\]

Endpoint slopes use one-sided differences; interior slopes use central differences on neighboring pair stations.

Angle of attack must be converted from degrees:

\[
\alpha = \texttt{alpha\_deg}\cdot\pi/180
\]

Lift and drag:

\[
C_L = C_n\cos\alpha - C_a\sin\alpha
\]

\[
C_D = C_n\sin\alpha + C_a\cos\alpha
\]

Do not use left-Riemann sums, do not treat `alpha_deg` as radians, and do not swap the Cl/Cd rotation.
