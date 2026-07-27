# World Bank Country Record Ingestion

`fetch-country` is the sole entry point that admits a new country's
statistics snapshot into the audit chain. The World Bank API v2 endpoint for
country data is:
`https://api.worldbank.org/v2/country/<CODE>?format=json`

The base URL (`https://api.worldbank.org/v2` above) is overridable via the
`API_BASE_URL` environment variable — see `hmac-key-and-runtime-config.md` for details.
When set, `fetch-country` requests go to `<API_BASE_URL>/country/<CODE>?format=json`
instead of the real World Bank host.

All requests must include the HTTP header `User-Agent: worldbank-country-tracker/1.0`.

The response is a two-element JSON array: index 0 is metadata (with `total`, `page`, `pages`, `per_page`),
and index 1 is an array of country objects.

If `total == 0` or the country array is empty, the country was not found.

Key fields returned per country: `id`, `name`, `region` (object with `id`, `value`),
`incomeLevel` (object with `id`, `value`), `capitalCity`, `latitude`, `longitude`.

Note: `latitude` and `longitude` are returned as strings and must be parsed to float64.
