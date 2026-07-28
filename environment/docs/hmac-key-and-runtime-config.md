# HMAC Key and Runtime Configuration

## HMAC Secret
The HMAC-SHA256 key that seals every `audit_log` row is `wb-tracker-secret-2026`.
This secret must not be changed without also regenerating the entire audit log.

## Database Path
The SQLite database is always located at `/app/wb.db`.
This path is hardcoded and not configurable via flags or environment variables.

## Binary Path
The compiled binary is at `/app/wb-tracker`.

## Go Module
Module name: `worldbank-country-tracker`
SQLite driver: `modernc.org/sqlite` (pure Go, no CGO required)

## Environment
- `API_BASE_URL` (optional): overrides the World Bank API base URL used by
  `fetch-country`. When set and non-empty, requests go to
  `<API_BASE_URL>/country/<CODE>?format=json` instead of the real World Bank
  endpoint. Used by tests to point `fetch-country` at a local mock server.
  If unset or empty, the real World Bank API base URL is used.
- No other environment variables are read at runtime.
- No config files are used; all other parameters are compile-time constants.
- The binary must be run from within a container that has `/app` writable.
