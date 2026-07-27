# Deployment Notes

The runtime described here exists to run the statistics engine offline
against a mocked record source, not to support local development.

## Module Cache
The Dockerfile populates the Go module cache from `environment/source/go.mod`
independently of any later source authored under `/app`, so module
resolution never needs network access after the image is built.

## Dependencies
- `modernc.org/sqlite`: pure-Go SQLite driver, no system library needed
- Standard library only for HTTP, HMAC, and CLI parsing
- No external frameworks required

## Verifying the Binary
```bash
/app/wb-tracker init
# Expected: OK
```
