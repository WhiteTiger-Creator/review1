Delta-method gain ratios against a reference lane with shared-source covariance.

# Reference-lane normalization

Absolute PMT gain depends on the pulser source, which drifts between runs. A profile may
therefore declare a `reference_lane`, in which case the published table carries each
lane's gain *relative* to that lane, where the common source cancels.

Normalization is a publication step. It runs on the fully reduced dataset, after every
lane has been fitted, and it changes no provenance counter and no fit. The report's
`normalized` field records which of the two modes below produced the `gain` column.

## Raw profiles

A profile with no `reference_lane` publishes `normalized = false` and copies the fitted
values straight through:

```
gain       = fitted gain          (ADC-sample per level)
gain_sigma = fitted gain sigma
```

## Normalized profiles

A profile with a `reference_lane` publishes `normalized = true`. Let `r` be the
reference lane's fitted gain and `var_r` its fitted gain variance, and `g`, `var_g`
those of the lane being normalized. Let

```
cov = shared_source_var       declared by the profile, default 0.0
```

be the covariance `cov(g, r)` induced by the pulser source driving both lanes.

**Ratio.**

```
gain = g / r
```

**Uncertainty.** First-order propagation of a ratio — the delta method — gives

```
var(q) = var_g / r^2
       + g^2 * var_r / r^4
       - 2 * g * cov / r^3

gain_sigma = sqrt(var(q))      published as 0.0 when var(q) <= 0
```

This is the expansion of `q^2 * ( var_g/g^2 + var_r/r^2 - 2*cov/(g*r) )`, written so that
a lane whose fitted gain is near zero does not divide by it.

The three terms are the lane's own variance, the reference lane's variance propagated
through the division, and the cross term. The cross term carries a minus sign: a source
fluctuation that lifts both gains together leaves the ratio unchanged, so a positive
shared covariance *reduces* the uncertainty on the ratio. Dropping it — or dividing the
raw sigma by `r` and stopping there — overstates the error on every lane of a normalized
profile.

The variances entering this expression are the fit's parameter variances, not the
squares of rounded published sigmas.

**The reference lane itself** publishes exactly

```
gain       = 1.0
gain_sigma = 0.0
```

These are exact constants, not the result of dividing the lane by itself: `r / r` equals
`1.0` only up to floating point, and the delta method applied to a perfectly correlated
pair is not defined here. A reference lane published as `0.999999999` is a contract
violation.

**Lanes that did not fit** — status `insufficient`, `noisy`, or `singular` — publish
`gain = 0.0` and `gain_sigma = 0.0`. They keep their row and their other columns; they
are simply not normalized.

## The reference lane is a run-level precondition

If a profile declares a `reference_lane`, the run cannot produce a meaningful table
without it. Each of the following aborts the entire run with `ValueError` before
anything is written:

| Condition |
|---|
| The declared reference lane has no row in the reduced dataset |
| The reference lane's fit status is not `ok` |
| The reference lane's fitted gain is not strictly positive |

No partial artifact is published in any of these cases: not a table with the reference
lane omitted, not a table falling back to raw gains, not a table normalized against some
other lane. The run fails, the reason goes to standard error, the exit status is `1`, and
any artifact already on disk is left untouched (`artifacts.md`).

This is deliberate. A calibration table whose reference is broken is not partially
correct — every ratio in it is meaningless — so publishing it would be worse than
publishing nothing.
