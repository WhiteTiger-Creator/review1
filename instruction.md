We already have a TypeScript vault engine under `/app/environment`. Play it to completion. This is output-only work, so do not modify `/app/environment` source.

Start a run with

```bash
node /app/environment/dist/src/main.js --seed nominal --out /app/output/vault_state.json
```

Commands on stdin (one per line) are `move <n|s|e|w>`, `look`, `take`, `use <shard_id>`, `attack`, and `exit`. Each successful command costs one turn. Budget is 220 turns.

Clash damage uses integer floor division

`damage = max(1, (atk * 3 + buff) / (1 + def))`

Observable state lines include floor index, position, pouch shard ids, used list, open_flag_epoch, apex_stage, apex_hp, turns_used, hp, here cell, and adjacent cell codes. Seeds are `nominal`, `holdout`, and `mirror`. Layouts differ by seed. Holdout also permutes which shard sits on which of the first three floors; catalog ids stay ember_core, veil_latch, crest_key.

Pouch apply rules (all required):

- `use ember_core` succeeds whenever that shard is in the pouch and unused.
- `use veil_latch` succeeds only after ember_core is already in the used list; otherwise the attempt removes veil_latch from the pouch without adding it to used (`STATUS use_spent_failed`).
- `use crest_key` succeeds only after veil_latch is already in the used list; otherwise crest_key is spent the same failed way.
- Successful crest_key use raises open_flag_epoch by 1. Ember and veil uses only raise buff.
- The apex fight only becomes winnable when open_flag_epoch is at least 1. Apex starts at 48 hp.

Stair seals (all required on floors that still have a ward or floor loot):

- Moving onto `>` descends only when every living ward on the current floor is gone.
- On the first three floors, descent also requires that floor's shard already taken into the pouch or already used.
- A sealed stair prints `STATUS stair_sealed need_ward_clear` or `STATUS stair_sealed need_floor_shard` and leaves you on the stair cell without descending.

Leave an adaptive driver at `/app/output/autoplay.js` that accepts `--seed` and `--out`, drives the engine over stdin/stdout for the requested seed, and writes `/app/output/trace_<seed>.txt` (one command per line). The graded path runs that driver for nominal, holdout, and mirror, then rechecks each transcript by replaying it through the engine into `/app/output/vault_state.json`, `/app/output/vault_state_holdout.json`, and `/app/output/vault_state_mirror.json`. Static transcript drops and hand-written JSON are not enough.

On exit the engine writes the `--out` JSON. Required fields follow.

- floors_cleared field must equal 5
- open_flag_epoch field must leave the locked zero value (raised epoch required)
- apex_stage field must equal "cleared"
- used_chain field must equal the comma-joined used list in apply order, which for a valid clear is `ember_core,veil_latch,crest_key`
- exit_seal_digest field equals the sha256 hex digest of UTF-8 bytes `seed|floors_cleared|apex_stage|turns_used|used_chain` (same digest the engine writes)
- turns_used field must remain inside the stated 220-turn budget
- seed field must equal the run seed

Notes under `/app/environment/docs/vault_manual.md` elaborate the same public contract with examples.
