# Regional Classification

Specification for the `tier` line printed by `country-rank` (see
`operations-reference.md` for the rest of that command's output).

## Core Slots Are Capped Per Region

Every country belongs to a `region` group (`countries.region`). At most 3
countries in a single region may hold the `core` tier at the same time; every
other country in that region holds `peripheral`. This cap is fixed at 3
regardless of how many countries end up sharing a region.

## Membership Is Live, Not Stored

`tier` is not a column and is never decided once and left alone. Every call
to `country-rank` re-derives the full membership of the queried country's
region from whatever rows are currently in the `countries` table. Fetching a
new country can change which countries in its region hold `core`, including
countries that were fetched and queried long before.

## Standing Within a Region

If a region has 3 or fewer countries, every country in it holds `core` (there
is no shortage of slots). If a region has more than 3 countries, each
country's standing is `abs(latitude - region_mean) / region_stddev`, where
`region_mean` and `region_stddev` are the population mean and population
standard deviation (divide by the region's own count, not count-1) taken over
latitude values of countries in that region only, never the whole table. If
the region's population standard deviation is exactly 0 (every country in the
region shares one latitude), every country's standing is 0.

## Selecting Core vs. Peripheral

Sort the region's countries by standing descending. Break ties by `code`
ascending. The first 3 countries in that order hold `core`; everyone else in
the region holds `peripheral`.

## Output

`country-rank <CODE>` prints a fourth line, `tier=core` or `tier=peripheral`,
after `pct=`.
