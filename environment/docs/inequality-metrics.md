# Inequality and Distribution Metrics

Numerical specifications for the inequality, concentration, and
distribution-shape measures computed over the `countries` table: each metric
fixes its normalization, log base, and rounding rule exactly, and results
must reproduce to the stated decimal places. All read-only; none modify the
database.

## country-gini

Computes the biased Gini coefficient of latitude values (treating all latitudes
as an income distribution after shifting to be non-negative).

Steps:
1. Load all latitude values and shift them: `shifted_i = lat_i - min(lats) + 1.0`
   (so all values are strictly positive)
2. Sort shifted values ascending, assign sequential ranks 1..N (no tie-breaking
   needed, use sort order rank)
3. Compute `rank_sum = sum(rank_i * shifted_i)` for i=1..N
4. `Gini = (2 * rank_sum) / (N * total_sum) - (N + 1) / N` where
   `total_sum = sum(shifted_i)`
5. Format to 8 decimal places. Print `insufficient_data` and exit 1 if N < 2.

Output: `gini=X.XXXXXXXX`

## country-entropy

Computes the Shannon entropy (base-2) of the region distribution. Counts the
number of countries per region. For each region with count `c_i` out of total
N: `p_i = c_i / N`. Entropy `H = -sum(p_i * log2(p_i))`. Uses base-2 logarithm
(NOT natural logarithm). Format to 8 decimal places. Print `insufficient_data`
and exit 1 if N < 2.

For a single-region distribution (K=1) the entropy is exactly zero and must
print as `entropy=0.00000000`, never `entropy=-0.00000000`; see
`float-formatting.md` for the negative-zero canonicalization rule this falls
under.

Output: `entropy=X.XXXXXXXX`

## country-atkinson

Computes the Atkinson index with epsilon=0.5 for the latitude distribution
(shifted to be strictly positive: `shifted_i = lat_i - min(lats) + 1.0`).

Formula: `A = 1 - (mean_of_sqrt_shifted)^2 / mean_shifted`

Where:
- `mean_shifted` = arithmetic mean of shifted values
- `mean_of_sqrt_shifted` = arithmetic mean of `sqrt(shifted_i)`

Format to 8 decimal places. Print `insufficient_data` and exit 1 if N < 2 or
`mean_shifted == 0`.

Output: `atkinson=X.XXXXXXXX`

## country-theil

Computes the Theil T entropy index over the latitude values stored in the
database.

Formula: `T = (1/N) * sum(xi/mu * ln(xi/mu))`

Where `xi = |latitude_i|` (absolute value of each latitude), `mu` = arithmetic
mean of all `|latitude|` values, and `ln` denotes the natural logarithm (base
e, NOT base 2). Uses absolute values directly — does NOT shift latitudes.
Format to 6 decimal places. If N < 2, prints `theil: NULL` and exits 0. If
`mu == 0`, prints `theil: NULL` and exits 0.

Output: `theil: X.XXXXXX`

## country-hhi

Computes the normalized Herfindahl-Hirschman Index of the region distribution.
Let `s_i = c_i / N` where `c_i` is the count of countries in region i and N is
the total number of countries. Let K be the number of distinct regions. Raw
`HHI = sum(s_i^2)`. Normalized `HHI = (raw_hhi - 1/K) / (1 - 1/K)`. Format to 8
decimal places. Print `insufficient_data` and exit 1 if N < 2 or K < 2
(normalization is undefined when all countries are in a single region).

Output: `hhi=X.XXXXXXXX`

## country-hoover

Computes the Hoover inequality index (also called the Robin Hood index) of the
latitude distribution stored in the `countries` table.

Steps:
1. Load all latitude values. Shift them to be strictly positive:
   `shifted_i = lat_i - min(lats) + 1.0`
2. Compute `mean_shifted` = arithmetic mean of shifted values (divide by N,
   NOT by N-1).
3. Compute `hoover = sum(|shifted_i - mean_shifted|) / (2 * sum(shifted_i))`

The denominator is `2 * sum(shifted_i)` (twice the total, NOT twice
`N*mean`). Format to exactly 8 decimal places. Print `hoover: NULL` and exit 0
if N < 2 or if `sum(shifted_i) == 0`.

Output: `hoover: X.XXXXXXXX`
