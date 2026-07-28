# Testing Guide

## Running Tests
Grading is executed via `/app/test.sh` inside the Docker container. The
harness first runs a full pipeline ingestion batch (init, a series of
`fetch-country` calls, then the analytics commands) and writes the results
to `/app/output/pipeline_report.json`. Grading fails outright if that report
file is missing, regardless of individual test outcomes. The rest of the
suite calls the `wb-tracker` binary directly and inspects stdout, exit
codes, and database state (`/app/wb.db`) for specific formulas and edge
cases.

## Test Categories
- **init**: verifies tables are created and `OK` is printed
- **fetch-country**: verifies successful insert, `exists` on duplicate, `not_found` on missing code
- **list-countries**: verifies tab-separated output ordering
- **country-stats**: verifies float formatting, NULL edge cases, stddev calculation
- **audit-verify**: verifies chain integrity and tamper detection for each reason type

## Key Edge Cases
- Fetching with lowercase code should store and print uppercase
- `country-stats` with 0 rows: all values are `NULL`
- `country-stats` with 1 row: `stddev_latitude=NULL`, rest computed
- `audit-verify` checks `seq_gap` before `prev_hash_mismatch` before `entry_hash_mismatch`
- `country-entropy` over a single-region dataset must print `entropy=0.00000000`,
  never `entropy=-0.00000000` (canonicalize negative zero before formatting;
  see `float-formatting.md`)
- `fetch-country` on a double-429 must print `rate_limited` to **stdout** (exit
  2), while `not_found: <CODE>` goes to **stderr** (exit 1) — these are opposite
  streams, see `rate-limiting.md`

## HTTP Mocking
In automated test environments, HTTP calls to the World Bank API are intercepted.
Tests inject known country data to ensure deterministic latitude/longitude values.
