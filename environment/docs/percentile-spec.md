# Percentile Calculation Specification

## Method: Nearest-Rank
The percentile calculation uses the nearest-rank method (not linear interpolation).

## Formula
Given N values sorted in ascending order and target percentile p (0 < p <= 1):
```
rank = ceil(p * N)
index = rank - 1
result = sorted_values[index]
```

## Examples
| N | Values         | p    | rank      | index | result |
|---|----------------|------|-----------|-------|--------|
| 4 | [10,20,30,40]  | 0.75 | ceil(3)=3 | 2     | 30     |
| 4 | [10,20,30,40]  | 0.90 | ceil(3.6)=4 | 3   | 40     |
| 5 | [1,2,3,4,5]    | 0.75 | ceil(3.75)=4 | 3  | 4      |
| 1 | [38.5]         | 0.75 | ceil(0.75)=1 | 0  | 38.5   |

## NULL Handling
- If count is 0, p75 and p90 print as `NULL`.
- If count >= 1, percentiles are always computable (rank >= 1 guaranteed by ceil).

## Applied Percentiles
- `p75_latitude`: 75th percentile of latitude values
- `p90_latitude`: 90th percentile of latitude values

## Median for p50_at_insert (Different Algorithm — Read Carefully)
The `audit_log.p50_at_insert` column (see `/docs/country-audit-schema.md` and
`/docs/hmac-spec.md`) is **not** computed with the nearest-rank method above.
It uses the standard statistical median with linear interpolation between the
two middle elements when N is even:

Given the existing `countries.latitude` values (before the row currently
being inserted) sorted ascending, with count N:
- If `N < 2`: `p50_at_insert = 0.0`.
- If `N` is odd: the middle element of the sorted array, 0-indexed at
  `(N-1)/2`.
- If `N` is even: the average of the two middle elements
  (`sorted[N/2 - 1]` and `sorted[N/2]`), with **HALF_EVEN (banker's)
  rounding** applied to 6 decimal places.

This value is recomputed before every insert (using only the rows already
present, not including the row about to be inserted) and is formatted to
exactly 6 decimal places wherever it appears (the `audit_log` table and the
HMAC chain message).
