# HMAC Chain Specification

## Algorithm
HMAC-SHA256, hex-encoded output (64 lowercase hex characters).

## Secret Key
`wb-tracker-secret-2026`

## Message Format
Each audit log entry's HMAC message is constructed as:
`<seq>|<country_code>|<latitude:.6f>|<longitude:.6f>|<skewness_at_insert>|<kurtosis_at_insert>|<p50_at_insert:.6f>|<mad_at_insert>|<prev_hash>`

- `seq`: integer sequence number (1-based)
- `country_code`: uppercase ISO code
- `latitude`, `longitude`, and `p50_at_insert`: formatted to exactly 6 decimal places (e.g., `38.526600`)
- `skewness_at_insert`: population skewness of existing latitude values formatted to 8dp, or `"NULL"` if N < 3 at insert time
- `kurtosis_at_insert`: excess population kurtosis of existing latitude values formatted to 8dp, or `"NULL"` if N < 4 at insert time
- `p50_at_insert`: median of all existing latitude values before this insert, formatted to 6 decimal places. This is a distinct algorithm from the nearest-rank percentile method used for `p75_latitude`/`p90_latitude` in `/docs/percentile-spec.md` — see that document's "Median for p50_at_insert" section for the exact odd/even rule and rounding mode.
- `mad_at_insert`: Median Absolute Deviation of all existing latitude values before this insert, formatted to exactly 8 decimal places, or the literal string `NULL` if N < 2 at insert time. Computed with the nearest-rank algorithm specified for the `country-mad` command in `/docs/advanced-statistics.md` (nearest-rank median as the center AND nearest-rank median of the absolute deviations) — this is NOT the interpolated HALF_EVEN median used for `p50_at_insert`.
- `prev_hash`: the `entry_hash` of the previous row, or 64 zero characters (`0000...0000`) for seq=1

## Chain Integrity
Each new entry's `prev_hash` must equal the previous entry's `entry_hash`.
This creates a tamper-evident chain; modifying any entry breaks all subsequent hashes.
