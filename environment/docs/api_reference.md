# API Reference

## CLI

```
make && ./bin/tuf-rollout-verifier [--help]
```

Writes `/app/output/rollout_report.json` on success (exit 0).

## Report schema

### config

| Field | Type | Source |
|-------|------|--------|
| `spec_version` | string | trust_policy.json |
| `reference_time` | string (ISO-8601 UTC) | trust_policy.json |
| `require_target_hashes` | boolean | trust_policy.json |
| `freeze_window_start` | string (ISO-8601 UTC) | trust_policy.json |
| `freeze_window_end` | string (ISO-8601 UTC) | trust_policy.json |
| `blocked_lanes` | string (comma-separated sorted lanes) | trust_policy.json |
| `allowed_lanes` | string (comma-separated sorted lanes) | trust_policy.json |

### roles[] (fixed order: root, timestamp, snapshot, targets)

| Field | Type |
|-------|------|
| `role` | string |
| `version` | integer |
| `status` | `valid` \| `expired` \| `invalid` |
| `signatures_ok` | integer |
| `signatures_required` | integer |
| `expired` | boolean |

### targets[] (sorted by `path`)

| Field | Type |
|-------|------|
| `path` | string |
| `length` | integer |
| `sha256` | string (lowercase hex) |
| `hash_match` | boolean |
| `lane` | string |
| `lane_blocked` | boolean |
| `freeze_blocked` | boolean |
| `rollout_eligible` | boolean |
| `min_snapshot_version` | integer |
| `max_snapshot_version` | integer (`-1` when unset) |
| `active_snapshot_version` | integer |

### summary

| Field | Type |
|-------|------|
| `roles_valid` | integer |
| `roles_total` | integer |
| `targets_listed` | integer |
| `targets_hash_ok` | integer |
| `targets_rollout_eligible` | integer |
| `targets_lane_blocked` | integer |
| `targets_freeze_blocked` | integer |
| `chain_intact` | boolean |
| `report_digest` | string (lowercase hex SHA-256) |

See `/app/docs/rollout_contract.md` for verification semantics.
