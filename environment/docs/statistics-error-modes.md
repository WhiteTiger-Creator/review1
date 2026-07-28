# Statistics and Ingestion Error Modes

Every error path below is either an ingestion failure (`fetch-country`) or a
chain-integrity failure (`audit-verify`); the two are never conflated.

## fetch-country
- If the World Bank API returns `total == 0` or an empty country array: print
  `not_found: <CODE>` to **stderr** (not stdout), exit 1.
- If the country code already exists in the database: print `exists`, exit 0.
- On successful insert: print `ok country=<CODE> name=<name>`, exit 0.
- Country codes are case-insensitive at input but stored and printed as uppercase.
- If the API returns HTTP 429 on both the initial request and the single retry: print
  `rate_limited` to **stdout** (not stderr), exit 2. This is the opposite stream from
  `not_found` above — see `rate-limiting.md` for the full retry sequence.

## audit-verify
- On chain integrity failure: print `TAMPERED seq=N reason=<type>`, exit 1.
- Tamper reasons checked in order: `seq_gap`, `prev_hash_mismatch`, `entry_hash_mismatch`.
- On success: print `ok chain_length=N`, exit 0.

## country-stats
- If count is 0: print all nine stat lines (see `statistics.md`/`operations-reference.md`) with `NULL` values where applicable.
- If count is 1: `stddev_latitude=NULL` and `stddev_longitude=NULL` (cannot compute stddev with fewer than 2 rows).
- All other floats formatted per `float-formatting.md`.

## init
- Always prints `OK` (uppercase) on success.
- Safe to run multiple times; uses CREATE TABLE IF NOT EXISTS.
