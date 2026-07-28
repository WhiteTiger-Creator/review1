# Architecture Overview

`wb-tracker` is the ingestion and analytics engine behind a small
data pipeline: it pulls country records from the World Bank API, lands them
in a SQLite table, and produces analytics/report output from that record
set. It has no external service dependencies at runtime.

## Components
- **Ingestion layer**: subcommands (`init`, `fetch-country`, `list-countries`) that pull records from the World Bank API v2 and land them in SQLite
- **Storage**: country records and a tamper-evident audit log persisted to `/app/wb.db` using `modernc.org/sqlite`
- **HMAC chain**: appends a tamper-evident audit entry on every successful record insert
- **Analytics/reporting layer**: subcommands (`country-stats`, `audit-verify`, `country-gini`, etc.) that read the stored records and print report output; a full pipeline run's output is captured in `/app/output/pipeline_report.json` (see `docs/testing.md`)

## Recompiling
After editing the source, recompile with `go build -o /app/wb-tracker .` inside `/app`. Module name is `worldbank-country-tracker`.
The `modernc.org/sqlite` driver is a pure-Go SQLite implementation with no CGO dependency.

## Data Flow
1. Pipeline run calls `fetch-country <code>` for each record in the ingestion batch
2. CLI normalizes code to uppercase, checks database for duplicates
3. HTTP GET to World Bank API with required User-Agent header
4. Parse JSON response, extract country fields
5. INSERT into `countries` table, then append row to `audit_log` with HMAC chain
6. Reporting commands read back the stored records to produce statistics, inequality metrics, and audit-chain verification output
