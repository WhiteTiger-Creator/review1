# Country Record Formats

Every numeric field that flows into a statistics computation or an HMAC
preimage must first pass through the exact parsing and formatting rules
below.

## ISO Country Codes
Two-letter uppercase ISO 3166-1 alpha-2 codes (e.g., `US`, `DE`, `BR`).
Input is case-insensitive; stored and displayed as uppercase.

## Latitude and Longitude
- Stored as REAL (float64) in SQLite
- API returns them as strings; must be parsed with `strconv.ParseFloat`
- Formatted to exactly 6 decimal places in HMAC messages and stats output

## Region and Income Level IDs
- `region`: populated from the `region.id` field in the API response (e.g., `NAC`, `LCN`, `ECS`)
- `income_level`: populated from `incomeLevel.id` (e.g., `HIC`, `UMC`, `LMC`, `LIC`)

## list-countries Output
Tab-separated columns in order: `code\tname\tregion\tincome_level\tcapital`
One line per country, no header row, sorted by name ASC then code ASC.

## country-stats Output
Plain key=value lines, one per line, no tabs or extra whitespace.
Float values use `%.6f` format. NULL values printed as the literal string `NULL`.
