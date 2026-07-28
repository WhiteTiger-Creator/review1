# Country and Audit-Chain Schema

## audit_log table
| Column       | Type                    | Notes                              |
|--------------|-------------------------|------------------------------------|
| seq          | INTEGER PRIMARY KEY     | Starts at 1, increments by 1       |
| country_code | TEXT                    | References countries.code          |
| latitude          | REAL                    | Snapshot at time of fetch                        |
| longitude         | REAL                    | Snapshot at time of fetch                        |
| kurtosis_at_insert| TEXT                    | Excess pop. kurtosis of existing latitudes (8dp) |
| skewness_at_insert| TEXT                    | Pop. skewness of existing latitudes (8dp)        |
| p50_at_insert     | REAL NOT NULL DEFAULT 0.0| Median of existing latitudes before insert; see the odd/even + HALF_EVEN rounding algorithm in `/docs/percentile-spec.md` ("Median for p50_at_insert") |
| mad_at_insert     | TEXT NOT NULL DEFAULT 'NULL'| Nearest-rank MAD of existing latitudes before insert (8dp, or `NULL` if N < 2); uses the `country-mad` algorithm in `/docs/advanced-statistics.md`, not the p50 median |
| prev_hash         | TEXT                    | Previous entry_hash (or 64 zeros)                |
| entry_hash        | TEXT                    | HMAC-SHA256 hex of this entry                    |

## countries table
| Column       | Type               | Notes                          |
|--------------|--------------------|--------------------------------|
| code         | TEXT PRIMARY KEY   | Uppercase ISO country code     |
| name         | TEXT               | Country display name           |
| region       | TEXT               | Populated from `region.id`     |
| income_level | TEXT               | Populated from `incomeLevel.id`|
| capital      | TEXT               | Capital city name              |
| latitude     | REAL               | Parsed from API string field   |
| longitude    | REAL               | Parsed from API string field   |
