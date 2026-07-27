# Statistics Reference

Numerical-methods reference for the descriptive-statistics commands. All
quantities are population (not sample) moments; percentiles use the
nearest-rank method; every value is formatted to a fixed decimal precision
with the rounding and signed-zero conventions of `/docs/float-formatting.md`.

## country-stats Output Format
`country-stats` always prints exactly 9 lines, in this order:
```
count=N
avg_latitude=X.XXXXXX
stddev_latitude=X.XXXXXX
p75_latitude=X.XXXXXX
p90_latitude=X.XXXXXX
skewness_latitude=X.XXXXXXXX
kurtosis_latitude=X.XXXXXXXX
p90_longitude=X.XXXXXX
stddev_longitude=X.XXXXXX
```
See `operations-reference.md` for a one-line summary. `skewness_latitude` and
`kurtosis_latitude` are formatted to 8 decimal places (like
`country-zscores`); all other float lines here use 6 decimal places.

## Standard Deviation
Population stddev (divide by N, not N-1):
`stddev = sqrt(sum((x - mean)^2) / N)`
Print `stddev_latitude=NULL` if fewer than 2 rows exist.
The same population formula applies to `stddev_longitude` (print `NULL` if fewer than 2 rows exist).

## Skewness (latitude)
Population skewness = `M3 / var^1.5`, where `M3 = sum((xi - mean)^3) / N` and
`var` is the population variance. Print `NULL` if N < 3 or `var == 0`.

## Kurtosis (latitude)
Excess population kurtosis = `M4 / var^2 - 3`, where `M4 = sum((xi - mean)^4) / N`.
Print `NULL` if N < 4 or `var == 0`.

## Nearest-Rank Percentile
For percentile p over N sorted values (ascending):
`rank = ceil(p * N)`, `index = rank - 1`

Example: 4 values [10, 20, 30, 40], p75:
`rank = ceil(0.75 * 4) = 3`, `index = 2`, result = 30.

## Float Formatting
`avg_latitude`, `stddev_latitude`, `p75_latitude`, `p90_latitude`, `p90_longitude`,
and `stddev_longitude` are formatted to exactly 6 decimal places using Go's `%.6f`
verb. `skewness_latitude` and `kurtosis_latitude` are formatted to exactly 8
decimal places using `%.8f` (see `float-formatting.md` for the general rule
and its z-score/skewness/kurtosis exceptions).
If count is 0, all stat lines print their value as `NULL` (not `0.000000`).
