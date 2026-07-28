# Advanced Statistics Reference

Numerical-methods specifications for the regression, time-weighted, and
correlation estimators computed over records in the `countries` table:
OLS fitting, exponentially weighted averaging with fixed intermediate
rounding, covariance/correlation with population normalization, and
robust dispersion (MAD). All read-only; none modify the database.

## country-forecast

Performs OLS (ordinary least-squares) linear regression over the rows
currently in the database, treating row position as the independent variable
and latitude as the dependent variable, then forecasts the latitude value at
position N+1.

Rows are ordered by `name ASC` then `rowid ASC`. Positions are 1-indexed: the
first row is position 1, second is position 2, etc. (The database `rowid` or
`AUTOINCREMENT` id is NOT used as the x value — sequential 1..N position
integers are used.) Format the forecast to 6 decimal places. If N < 2, prints
`forecast: NULL` and exits 0.

OLS formulas:
- `slope = (N * sum(xi*yi) - sum(xi) * sum(yi)) / (N * sum(xi^2) - sum(xi)^2)`
- `intercept = (sum(yi) - slope * sum(xi)) / N`
- `forecast = intercept + slope * (N+1)`

Output: `forecast: X.XXXXXX`

## country-covar

Computes the population covariance between latitude and longitude values
stored in the `countries` table.

Formula: `covar = (1/N) * sum((lat_i - mean_lat) * (lon_i - mean_lon))` where
`mean_lat` and `mean_lon` are the arithmetic means. Divides by N (population
covariance), NOT by N-1 (sample covariance). Format to 8 decimal places. Print
`covar: NULL` and exit 0 if N < 2.

Output: `covar: X.XXXXXXXX`

## country-ewma

Computes an exponentially weighted moving average (EWMA) of latitude values.

Parameters: alpha = 0.3. Rows are ordered by `code ASC`. Seeds the EWMA from
the first latitude (the row with the smallest country code). For each
subsequent row (in code ASC order): `ewma = alpha * lat_i + (1 - alpha) *
ewma`. After each update step (including the seed), applies HALF_EVEN
(banker's) rounding to 6 decimal places before using the value in the next
step. Format final output to 6 decimal places. Print `ewma: NULL` and exit 0
if there are no countries in the database.

Output: `ewma: X.XXXXXX`

## country-weighted-stats

Computes a position-weighted latitude statistic.

Loads all latitude values from the `countries` table, ordered by `name ASC`
then `code ASC`. Assigns 1-indexed positions i=1,2,...,N to each row.

Computes:
- `weighted_sum = sum(i * lat_i)` for i=1..N
- `denom = N * (N + 1) / 2` (= 1+2+...+N)
- `W = weighted_sum / denom` (position-weighted mean)
- `M = sum(lat_i) / N` (arithmetic mean)
- `momentum = W / M` if M != 0, else `0.000000`

Output:
```
weighted_mean=X.XXXXXX
mean=X.XXXXXX
momentum=X.XXXXXX
```

Print `insufficient_data` and exit 1 if N < 2. If M == 0, print
`momentum=0.000000`. Format all values to exactly 6 decimal places using
banker's rounding (round-half-to-even). Exit 0 on success.

## country-pearson

Computes the Pearson correlation coefficient between the 1-indexed sequential
position of each country (ordered by `code ASC`, position 1 = smallest code)
and its latitude value.

Formula: `r = (N*sum(xi*yi) - sum(xi)*sum(yi)) / sqrt((N*sum(xi^2) -
sum(xi)^2) * (N*sum(yi^2) - sum(yi)^2))`

where `xi` = sequential position (1, 2, ..., N) and `yi` = latitude of the
i-th row (in code ASC order). Format the result to exactly 8 decimal places
using HALF_EVEN (banker's) rounding. Print `pearson: NULL` and exit 0 if N < 2
or if the denominator is zero (i.e., either series has zero variance).

Output: `pearson: X.XXXXXXXX`

## country-autocorr

Computes the lag-1 autocorrelation of latitude values ordered by `code ASC`.

Formula: `autocorr = cov1 / pop_var`

where:
- `mean` = arithmetic mean of all N latitude values
- `cov1 = sum_{t=0}^{N-2}((y_t - mean) * (y_{t+1} - mean)) / N`
  (population-style, divide by N)
- `pop_var = sum_{t=0}^{N-1}((y_t - mean)^2) / N`
  (population variance of all N values)

Format to exactly 8 decimal places using HALF_EVEN (banker's) rounding. Print
`autocorr: NULL` and exit 0 if N < 2 or if `pop_var == 0`.

Output: `autocorr: X.XXXXXXXX`

## country-mad

Computes the Median Absolute Deviation (MAD) of latitude values stored in the
`countries` table.

Steps:
1. Load all latitude values.
2. Find the median using nearest-rank: `rank = ceil(0.5 * N)`,
   `index = rank - 1` (0-based index into sorted array).
3. Compute absolute deviations: `dev_i = |lat_i - median|`.
4. Find the median of the absolute deviations using the same nearest-rank
   rule.

Format to exactly 8 decimal places. Print `mad: NULL` and exit 0 if N < 2.

Output: `mad: X.XXXXXXXX`
