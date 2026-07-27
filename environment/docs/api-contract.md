# Local API contract

The HTTP daemon (`opsd`) binds to loopback by default at `127.0.0.1:9470`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/v1/records` | Store a record (`{"payload": "..."}`) |
| GET | `/v1/records/{id}` | Read current-generation record |
| POST | `/v1/readers` | Open a reader snapshot, returns `token` |
| GET | `/v1/readers/{token}/records/{id}` | Read via pinned snapshot |
| DELETE | `/v1/readers/{token}` | Release reader pin |
| POST | `/v1/upgrade/start` | Start online upgrade |
| POST | `/v1/upgrade/recover` | Run recovery planner |
| POST | `/v1/upgrade/cleanup` | Run generation cleanup |
| GET | `/v1/status` | Status report (same fields as CLI) |

`GET /v1/status` and `opsctl status --json` share the same field set:

- `database_path`, `schema_version`
- `current_generation`, `published_generation`
- `upgrade_phase`, `upgrade_id`
- `active_reader_count`
- `generation_states`

## Reader tokens

Reader tokens returned by `POST /v1/readers` are durable across daemon restart. A token opened before an upgrade pins the reader to the generation active at open time. Closing a reader releases the pin.

## Error responses

Errors return HTTP 400 with JSON body:

```json
{"error": "description", "code": "not_found|invalid_state|incompatible|error"}
```

## Audit log

Structured audit entries are appended to the path configured as `audit_path` (default `/app/state/store.audit.jsonl`). Each line is JSON with fields:

- `timestamp`, `operation`, `upgrade_id`, `phase`, `outcome`
- `source_generation`, `target_generation`, `reader_count`, `reason_code`

## Environment variables

| Variable | Purpose |
|---|---|
| `KSEAL_CONFIG` | Path to service.toml (default `/app/config/service.toml`) |
| `KSEAL_DB` | Default database path |
| `KSEAL_AUDIT` | Default audit log path |
| `KSEAL_FAILPOINT` | Documented crash barrier name |
