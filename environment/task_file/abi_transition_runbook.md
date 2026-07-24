# Runtime ABI transition release runbook

This is the authoritative release-engineering specification for interpreting the supplied monorepo dependency inventories, scheduling rebuild and validation tickets, controlling temporary ABI bridges, comparing feasible rollouts, and recording approved manifests. All calculations use signed 64-bit integer arithmetic.

## Inventory records

Inventories are whitespace-separated text. Ignore blank lines and lines beginning with `#`. Every supplied inventory has a feasible rollout and contains no more than 12 waves, 4 actions per wave, 12 packages, 24 dependency rows, and 8 bridge rows.

- `PARAM wave_count W`
- `PARAM max_actions_per_wave A`
- `PARAM max_bridge_mb M`
- `PARAM max_rollback_mb R`
- `WAVE index build_minutes test_minutes old_multiplier burnin_multiplier`
- `PACKAGE package_id owner failure_domain safe_rebuild_minutes fast_rebuild_minutes validate_minutes old_exposure_weight safe_burnin_weight fast_burnin_weight safe_rollback_mb fast_rollback_mb`
- `DEP consumer_id provider_id`
- `BRIDGE provider_id enable_minutes disable_minutes storage_mb carrying_cost`

Parameters are positive integers. There is one `WAVE` row for every 1-based wave index from 1 through `W`, in that order. Package IDs are unique; every dependency pair is unique; and a provider has at most one bridge row. Identifiers are non-empty case-sensitive ASCII tokens. Numeric record fields are non-negative, all references are valid, and every intermediate and final calculation fits a signed 64-bit integer.

## Build and release tickets

Initially every package uses the old ABI, no rebuilt package is validated, and no bridge is active. A manifest contains exactly `W` waves. A wave may be empty and otherwise contains at most `A` distinct tickets chosen from:

- `REBUILD_SAFE_<package_id>`
- `REBUILD_FAST_<package_id>`
- `VALIDATE_<package_id>`
- `BRIDGE_ON_<provider_id>`
- `BRIDGE_OFF_<provider_id>`

Every package chooses exactly one rebuild mode and is validated exactly once. A safe or fast rebuild uses the corresponding build minutes, burn-in weight, and rollback storage from its `PACKAGE` row. Validation uses `validate_minutes` of test capacity. Bridge activation and retirement use their respective build minutes.

A package can be validated only if it was rebuilt before the current wave, so rebuilding and validating it together is invalid. A bridge can be enabled at most once, can be retired only while active, cannot be re-enabled, and must be retired by the end. Activation and retirement of the same bridge cannot share a wave.

## End-of-wave feasibility

Tickets within a wave are simultaneous. Apply them together, then check the resulting state:

- Total build and test minutes do not exceed the wave's respective capacities.
- At most one rebuild or validation ticket targets a given `failure_domain` in that wave.
- Active bridge storage is at most `max_bridge_mb`.
- Rollback storage for rebuilt but unvalidated packages is at most `max_rollback_mb`, using each selected rebuild mode's rollback value.
- For every `DEP consumer provider`, if consumer and provider have different ABIs, the provider's bridge is active.
- A package is validated only when all its direct providers are validated by the end of the wave. Provider and consumer validations in the same wave satisfy this rule.

A bridge may be activated in the wave that first creates its ABI mismatch and retired in the wave that removes the final mismatch it covers.

## Cost and canonical choice

After each wave, add all of the following to `migration_cost`:

1. The wave's `old_multiplier * old_exposure_weight` for every package still on the old ABI.
2. The wave's `burnin_multiplier` times the chosen mode's burn-in weight for every rebuilt but unvalidated package.
3. The `carrying_cost` of every active bridge.

Among feasible manifests, choose the lowest `migration_cost`, then the lowest peak active bridge storage, then the lowest peak rollback storage, then the lowest total minutes of all selected rebuild, validation, bridge-on, and bridge-off tickets. If still tied, compare wave 1's sorted ticket-ID array, then wave 2's, and so on. Arrays use ordinary case-sensitive lexicographic comparison, with a proper prefix smaller.

## Release manifest schema

Write one JSON object per inventory with exactly these top-level fields:

- `migration_cost`: integer.
- `peak_bridge_mb`: integer maximum active bridge storage after any wave.
- `peak_rollback_mb`: integer maximum rollback storage after any wave.
- `total_action_minutes`: integer total minutes of every selected ticket.
- `waves`: exactly `W` entries in ascending wave order.

Each wave entry has exactly:

- `wave_index`: its 1-based integer index.
- `action_ids`: selected ticket IDs sorted in ASCII lexicographic order.
- `build_minutes`: integer build minutes used by the wave.
- `test_minutes`: integer test minutes used by the wave.
- `active_bridge_package_ids`: sorted provider IDs whose bridges are active after the wave.
- `remaining_old_package_ids`: sorted package IDs still using the old ABI after the wave.
- `awaiting_validation_package_ids`: sorted rebuilt but unvalidated package IDs after the wave.
- `validated_package_ids`: sorted validated package IDs after the wave.

The last three package arrays partition all packages. Use lowercase JSON syntax and preserve every field name exactly.
