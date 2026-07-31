# Vault manual

Public contract already stated in the task instruction. This note expands examples only.

## Commands

- `move n|s|e|w` step one cell
- `look` inspect current and adjacent cells; prints `SHARD_TEXT` when standing on a remaining shard slot
- `take` pick up a shard on the current cell into the pouch
- `use <shard_id>` attempt a pouch apply step (failed chain attempts spend the shard)
- `attack` strike a ward on the current cell, or the apex when standing on `X`
- `exit` seal the run and write the output JSON (even if apex_stage is still locked or open)

## Stair seals

Descent on `>` requires the current floor ward cleared. On the first three floors it also requires that floor's shard already collected. Floor-to-shard placement is seed-dependent; do not assume floor index equals catalog order.

## Pouch chain

Apply order is ember_core, then veil_latch, then crest_key. Wrong-order `use` removes the shard from the pouch without marking it used, which soft-locks a clear if that was the only copy.

## Damage

Same integer floor-division damage relation as the instruction. Apex hp starts at 48.

## Completion fields

Output JSON must show floors_cleared 5, open_flag_epoch at least 1, apex_stage cleared, used_chain `ember_core,veil_latch,crest_key`, turns_used at most 220, matching exit_seal_digest (sha256 hex of `seed|floors_cleared|apex_stage|turns_used|used_chain`), and the run seed.

Driver and transcript artifacts live under `/app/output/` including `autoplay.js`, `trace_<seed>.txt`, and the vault_state JSON files named above. Grading may also write short scratch logs such as `engine_hits.log` under `/app/output/` while confirming the driver actually launches `node /app/environment/dist/src/main.js`.
