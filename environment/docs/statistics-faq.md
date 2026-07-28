# Statistics Engine FAQ

These are the recurring questions about how the audit chain and the
statistics operations interact.

## Q: Why does fetch-country print `exists` instead of updating the record?
The tracker is designed to store a snapshot of country data at first fetch.
Subsequent calls for the same code are no-ops to preserve the audit chain integrity.

## Q: What happens if the World Bank API is unreachable?
The binary will exit with a non-zero status code and print an error to stderr.
No database changes are made on failed HTTP requests.

## Q: Can I use a 3-letter (ISO 3166-1 alpha-3) country code?
No. The World Bank API endpoint uses 2-letter alpha-2 codes.
Passing a 3-letter code will likely return `not_found`.

## Q: Why is stddev computed with N instead of N-1?
The task uses population standard deviation (dividing by N), not sample stddev (N-1).
This is consistent with treating the stored countries as a complete population.

## Q: What does the `seq_gap` tamper reason mean?
It means the `seq` values in `audit_log` are not consecutive (e.g., 1, 2, 4 — missing 3).
This indicates a row was deleted from the audit log.

## Q: Is the database schema created automatically?
Only when `init` is explicitly called. The other commands assume the tables exist.

## Q: What timezone are timestamps stored in?
UTC. All timestamp fields use RFC3339 format with a Z suffix.

## Q: Are HTTP retries performed?
No; a single request is made per API call, and failures propagate to the caller.

## Q: Does the tool support pagination?
No; the World Bank API responses are fetched in full for the requested indicator/country pair.

## Q: Is caching used for repeated indicator lookups?
No; every command issues a fresh HTTP request.
