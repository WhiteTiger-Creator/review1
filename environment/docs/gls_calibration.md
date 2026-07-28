Three-parameter GLS with shared-pedestal common-mode covariance.

# Generalized least squares gain fit

Each lane is fitted independently from the observations admitted in
`rolling_pedestal.md`. The fit is a *generalized* least squares problem, not a weighted
one: observations corrected against the same pedestal population share a correlated
pedestal error, and a per-point weight cannot express that.

Constants used here: `MIN_OBS = 6`, `MIN_DISTINCT_LEVELS = 3`,
`COMMON_MODE_SCALE = 0.25`, `COND_THRESHOLD = 1e12`.

## Model

For the `n` observations of one lane, with pedestal-corrected charges `q_i`, drive
levels `L_i`, and acquisition times `t_i` in seconds:

```
q_i = intercept + gain * L_i + drift * (t_i - t0) + e_i
```

The time origin is the **mean** of that lane's own observation times:

```
t0 = (t_1 + t_2 + ... + t_n) / n
```

`t0` is per lane and is computed from the admitted observations only — not the run
start, not the first timestamp, not a value shared between lanes. Centring the time
regressor decorrelates `drift` from `intercept` and keeps the normal equations
conditioned. `t0` is published so the drift term can be evaluated by a reader.

Three parameters are always fitted together. The intercept is never forced through the
origin: a residual pedestal offset must be free to absorb into it, and suppressing it
biases the gain. The design matrix has one row per observation:

```
X_i = [ 1, L_i, t_i - t0 ]
```

## Classification before fitting

Let `n` be the number of admitted observations, `distinct_levels` the number of
distinct drive levels among them, and `noisy_rejections` the number of pulsers this
lane lost to the pedestal noise test.

| Order | Condition | Status |
|---|---|---|
| 1 | `n < MIN_OBS` and `noisy_rejections > 0` | `noisy` |
| 2 | `n < MIN_OBS` or `distinct_levels < MIN_DISTINCT_LEVELS` | `insufficient` |

The order matters. A lane starved of observations *because* its pedestal was unusable is
reported as `noisy`, which names the cause; a lane that simply had too few acquisitions,
or too few distinct levels to separate gain from intercept, is `insufficient`. A lane
that reached `MIN_OBS` observations is fitted normally even if some of its pulsers were
rejected as noisy along the way.

`distinct_levels` counts distinct levels, not observations: a lane with many points at
two levels cannot determine three parameters, however many points it has.

## Measurement covariance

Let `V` be the `n x n` measurement covariance.

**Diagonal.** `V[i][i] = variance_i`, the per-observation variance frozen at admission
(gate charge variance plus the coverage-scaled pedestal variance).

**Common mode.** Group the observations by their frozen epoch. For every group `G` with
at least two members,

```
c_G = COMMON_MODE_SCALE * mean( variance_i for i in G )
```

is added to every off-diagonal entry `V[i][j]` with `i != j` and both `i, j` in `G`.
Groups of one member contribute nothing, the diagonal is never modified by this step,
and observations in different groups stay uncorrelated.

The physical content is that a shared pedestal estimate carries a shared error: two
observations corrected by the same window are wrong in the same direction by part of the
same amount. Ignoring the block leaves the fit believing it has more independent
information than it has, which is what makes quoted uncertainties implausibly small on
lanes with many observations against one pedestal.

## Solving

The covariance is never inverted. Factor it and whiten by triangular solves:

```
V = L * L^T                      (Cholesky, L lower triangular)
solve L * Xw = X    for Xw
solve L * qw = q    for qw
A    = Xw^T * Xw                 (this is X^T V^-1 X, formed without V^-1)
beta = solve(A, Xw^T * qw)       beta = [ intercept, gain, drift ]
```

If the Cholesky factorization or any of these solves fails — `V` is not positive
definite, or `A` is singular — the lane is reported as `singular` and nothing is
published for it.

## Conditioning

The 1-norm condition number of the normal-equation matrix,

```
cond = ||A||_1 * ||A^-1||_1
```

is computed and published. If it is not finite, or if `cond > COND_THRESHOLD`, the lane
is `singular`. This is the guard that catches a lane whose drive level advances in
lockstep with acquisition time: there `level` and `t - t0` are collinear, gain and drift
cannot be separated, and the split between them is arbitrary. Such a lane must be
reported as `singular`, not fitted with a confident-looking pair of numbers.

## Diagnostics and uncertainties

The residual is formed in the original space and then whitened, so that `chi2` is the
quadratic form under the full covariance:

```
r    = q - X * beta
rw   = solve(L, r)
chi2 = rw^T * rw                 (equivalently r^T V^-1 r)
dof  = n - 3
chi2_per_dof = chi2 / dof        published as null when dof <= 0
```

On a lane whose variances are honest, `chi2` lands near `dof`. A `chi2` computed from
unweighted residuals, or from weights that ignore the common-mode block, does not.

The parameter covariance is the inverse Gram matrix `A^-1`. The published uncertainties
are the square roots of its diagonal, and a non-positive diagonal entry publishes `0.0`:

```
intercept_sigma = sqrt( A^-1[0][0] )
gain_sigma      = sqrt( A^-1[1][1] )
drift_sigma     = sqrt( A^-1[2][2] )
```

The covariance is **not** rescaled by `chi2 / dof`. The observation variances are the
measurement model, and the fit reports the uncertainty that model implies; `chi2_per_dof`
is published separately so a reader can judge whether the model held. The gain variance
`A^-1[1][1]` is also what the delta method consumes in `lane_scale.md`.

## Statuses

| Status | Meaning |
|---|---|
| `ok` | fitted; parameters, uncertainties, `chi2`, `dof`, `chi2_per_dof`, and `cond` are published |
| `noisy` | fewer than `MIN_OBS` observations, with at least one pulser lost to the pedestal noise test |
| `insufficient` | fewer than `MIN_OBS` observations, or fewer than `MIN_DISTINCT_LEVELS` distinct levels |
| `singular` | Cholesky or solve failure, or `cond` not finite, or `cond > COND_THRESHOLD` |

A lane that is not `ok` still occupies a row. It publishes `0.0` for every fitted
parameter, every sigma, `t0`, `chi2`, and `cond`; `0` for `dof`; and `null` for
`chi2_per_dof`. Its `n_obs` and `distinct_levels` remain the counts it actually
gathered.

A lane that fails to fit never removes another lane from the table and never aborts the
run — with the single exception of a reference lane, handled in `lane_scale.md`.
