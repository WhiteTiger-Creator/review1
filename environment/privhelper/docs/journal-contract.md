# Journal contract

Append-only JSONL files:

- `/app/var/privhelper/journal.jsonl`
- `/app/var/privhelper/decisions.jsonl`
- `/app/var/privhelper/effects.jsonl`

Every line is one JSON object. Do not truncate or rewrite evidence during normal operation or recovery. `reset` may recreate the scenario from fixtures.

## Event kinds

`prepared`, `effect_applied`, `committed`, `denied`, `conflict`, `recovery_denied`

## Common event fields

Every journal event includes:

- `event_seq` — monotonically increasing
- `event` — kind above
- `request_id`, `request_digest`
- full canonical request fields: `principal`, `action`, `unit`
- `manifest_generation`, `manifest_digest` used by that transition
- `helper_name`, `helper_digest` when applicable
- `decision`, `outcome`, `reason` when applicable

## Allowed successful path (durable sync at each step)

1. Append `prepared`
2. Execute verified helper
3. Append exactly one effect ledger row
4. Append `effect_applied`
5. Append decision ledger row
6. Append `committed`

Deny / conflict paths append a decision and a `denied` or `conflict` journal event and never append an effect.

## Crash points

- After `prepared`: no helper execution, no effect, no decision/`committed`
- After `effect` / `effect_applied`: exactly one effect exists; decision/`committed` are absent

Ledger writes must flush and sync before the next security transition so crash injection is deterministic.

## Decision ledger row

Includes at least: `seq`, `request_id`, `request_digest`, `principal`, `action`, `unit`, `decision` (`allow`|`deny`|`conflict`), `outcome`, `reason`, helper identity fields, manifest generation/digest, `launch_surface`.

## Effect ledger row

Includes at least: `seq`, `request_id`, `request_digest`, `principal`, `action`, `unit`, `effect`, helper identity fields, manifest generation/digest.

Exactly one effect row may exist per successfully applied `(request_id, request_digest)`. Denied or conflicting requests never have an effect row.
