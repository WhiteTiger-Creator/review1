# Statistics Engine Operations Reference

The wb-tracker subcommands span three tiers: record ingestion, descriptive
and inequality statistics, and audit-chain verification.

## init
Creates the `countries` and `audit_log` tables in SQLite if they do not exist.
Prints `OK` on success. Safe to run multiple times (idempotent).

## fetch-country <CODE>
Fetches country data from the World Bank API using the given ISO code (case-insensitive).
Stores the country in the `countries` table and appends an audit log entry.
Prints `ok country=<CODE> name=<name>` on success, `exists` if already stored.
If the API returns no data, prints `not_found: <CODE>` to **stderr** (not stdout) and exits 1.
Handles HTTP 429: waits `Retry-After` seconds (default 1), retries once. If retry also 429: prints
`rate_limited` to **stdout** (not stderr) and exits 2 — this is the opposite stream from `not_found`
above; see `rate-limiting.md` for the full retry sequence.

## list-countries [--limit N] [--offset M]
Prints all stored countries as tab-separated lines ordered by `name ASC`, then `code ASC`.
Columns: `code`, `name`, `region`, `income_level`, `capital`.
Optional flags: `--limit N` (return at most N rows), `--offset M` (skip first M rows after sorting).

## country-stats
Prints 9 lines of aggregate statistics over the `latitude` and `longitude` columns.
Includes count, average, population stddev, p75, p90, skewness, kurtosis (latitude) and p90, stddev (longitude).

## country-zscores
Prints per-country z-scores for latitude and longitude, sorted by z_lat ASC then code ASC.
Output: `<CODE>\t<z_lat>\t<z_lon>` per line, one line per country.
`z_lat`/`z_lon` are formatted to **8 decimal places** (`%.8f`) — see `float-formatting.md`
for the exact formula and the 8dp exception to the general 6dp rule.
Prints `insufficient data` if fewer than 2 countries are stored.

## country-rank <CODE>
Prints the 1-based rank of a country by latitude ascending (ties broken by code ASC).
Output: `rank=N`, `total=M`, `pct=X.XX`, `tier=<core|peripheral>`. The `tier`
line reflects the country's current standing within its own region, capped
and re-derived on every call; see `regional-classification.md` for the full
rule.
Prints `not_found` and exits 1 if the code is not in the database.

## audit-verify
Verifies the HMAC-SHA256 chain stored in `audit_log`.
Prints `ok chain_length=N` or `TAMPERED seq=N reason=<type>` and exits 1 on failure.

## audit-stats
Prints a summary of the `audit_log` table:
`chain_length=N`, `unique_codes=M`, `first_code=<CODE>`, `last_code=<CODE>`.
Prints `first_code=none` and `last_code=none` if the log is empty.

## country-chain-dual
Prints forward and reverse HMAC chain terminal hashes (`fwd=`, `rev=`).
Full spec, including the reverse-chain key and message format, in `chain-spec.md`.

## audit-baseline-window
Prints a live `baseline`/`provisional` reference-set status per `audit_log`
row, bounded by a fixed-size window with delayed age-out. Full spec,
including the window size and age-out delay constants, in
`audit-baseline-window.md`.

## Inequality and Distribution Commands
`country-gini`, `country-entropy`, `country-atkinson`, `country-theil`,
`country-hhi`, and `country-hoover` each compute a distributional inequality
or concentration statistic over stored latitude or region values. Full
formulas, output formats, and NULL/insufficient-data rules are in
`inequality-metrics.md`.

## Advanced Statistics Commands
`country-forecast`, `country-covar`, `country-ewma`, `country-weighted-stats`,
`country-pearson`, `country-autocorr`, and `country-mad` each compute a
regression, time-weighted, or correlation statistic over stored country
records. Full formulas, output formats, and NULL/insufficient-data rules are
in `advanced-statistics.md`.
