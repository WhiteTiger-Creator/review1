# Float Formatting Rules

## General Rule
Most floating-point output values are formatted to exactly 6 decimal places using `%.6f`.
`country-zscores` (`z_lat`/`z_lon`) and the `skewness_latitude`/`kurtosis_latitude`
lines of `country-stats` are explicit exceptions: they are formatted to
**8 decimal places** using `%.8f` (see "Exceptions" below).

## Applies To (6dp)
- `avg_latitude` in `country-stats`
- `stddev_latitude` in `country-stats`
- `p75_latitude` in `country-stats`
- `p90_latitude` in `country-stats`
- `p90_longitude` in `country-stats`
- `stddev_longitude` in `country-stats`
- `latitude` and `longitude` in HMAC message construction

## Exceptions (8dp)
`z_lat`/`z_lon` (from `country-zscores`) and `skewness_latitude`/`kurtosis_latitude`
(from `country-stats`) are formatted to exactly 8 decimal places using `%.8f`,
not the general 6dp rule above:
```
z_lat  = (latitude - mean_latitude) / stddev_latitude    → e.g. 1.22474487
z_lon  = (longitude - mean_longitude) / stddev_longitude → e.g. -0.70710678
```
Print `NULL` for `z_lat`/`z_lon` if the corresponding stddev is 0.
See `operations-reference.md` for the full `country-zscores` output spec and `statistics.md`
for the skewness/kurtosis formulas.

## Examples
```
38.5266    → 38.526600
-15.0      → -15.000000
0.0        → 0.000000
51.509865  → 51.509865
```

## HMAC Message Requirement
In the HMAC message string, latitude and longitude MUST use `%.6f` format.
Using the raw Go float representation (e.g., `38.5266` instead of `38.526600`) will produce
a different hash and cause `entry_hash_mismatch` failures in `audit-verify`.

## NULL Values
When a stat cannot be computed (count=0, or stddev with <2 rows),
print the literal string `NULL`, not `0.000000` or an empty string.

## Zero Results Must Never Print as Negative Zero
A mathematically-zero result must always be canonicalized to positive zero
before formatting: printed output is `0.00000000` / `0.000000`, never
`-0.00000000` / `-0.000000` (IEEE 754 negative zero is not an acceptable
formatted value). This applies to every command in this file's
"Applies To"/"Exceptions" lists.
