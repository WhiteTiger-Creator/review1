# Rate Limiting and API Constraints

## World Bank API Limits
The World Bank API is a public API with no authentication required.
However, it enforces rate limits on excessive automated traffic.

## HTTP 429 Handling (Required)
If the API returns HTTP 429 (Too Many Requests), the `fetch-country` command must:
1. Read the `Retry-After` response header (integer seconds; default to 1 if missing or invalid).
2. Sleep exactly that many seconds using `time.Sleep`.
3. Retry the request exactly once.
4. If the retry also returns 429: print `rate_limited` to **stdout** (not stderr) and exit with code 2.
5. If the retry succeeds: proceed normally with the response.

The tool must not retry more than once. The `Retry-After` sleep duration must be honored exactly.
Note this is the opposite stream from the `not_found: <CODE>` case (see `operations-reference.md` and
`statistics-error-modes.md`), which goes to **stderr**: only `not_found` is a stderr message, `rate_limited`
is always stdout, exit code 2.

## Recommended Practices
- Fetch one country at a time; avoid parallel bulk requests.
- The `fetch-country` command exits early (`exists`) if the country is already stored, avoiding redundant API calls.

## Offline / Test Environments
In test environments, the World Bank API endpoint may be stubbed or blocked.
The test harness may mock HTTP responses to ensure deterministic behavior.
Do not rely on live API availability in automated test suites.

## User-Agent Header
Every request must include: `User-Agent: worldbank-country-tracker/1.0`
Omitting this header may result in rejected or throttled requests.
