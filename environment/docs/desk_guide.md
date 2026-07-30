# Desk guide

## Artifacts
`turn_trace.json` holds a wave integer and a rows list. Each row carries id, kind, actor, target, pid, and slot. `field_state.json` holds wave, an actors map (hp and pos per id), a tiles map (mod per id), and checksum. Forms under `/app/environment/forms/` mirror those shapes. Causal parents must form a tree: every non-null pid refers to an earlier row id.

## Checksum
`field_state.checksum` is the lowercase hex sha256 (also written SHA-256) of the UTF-8 payload `wave|id1,id2,...` where the ids are the emitted row ids in transcript order. The digest is always 64 hex characters. The same digest may be recomputed with hashlib.sha256.

## Resume
During play, each committed row is appended to `/app/environment/data/.warm/journal.jsonl`. `play --resume` must rebuild committed state from that journal and continue so the final `turn_trace.json` and `field_state.json` match a from-scratch play, including checksum. A clean `play` (without `--resume`) must ignore any leftover journal bytes and start fresh, so a planted stale row id such as `__stale__` must not appear in the regenerated transcript. Resume rebuild must preserve open-strike board frames and lethal gates the same way a live resolve would, not re-read live tile mods for already committed strikes.

## Round rules
Primary jobs run highest actor init first. Equal init breaks by actor id ascending, then job id ascending. Jobs marked `void` true are omitted from the primary sequence and leave no transcript row.

Hooks with `when` equal to `on_strike` and `vs` equal to the struck target interrupt under that strike. Nested rows set `pid` to the parent strike id. All nested work for a strike finishes before later primary jobs. Parent strike damage lands only after its nested hooks finish. Hooks marked `void` true leave no row.

When a strike opens, freeze a board-mod frame for that whole strike tree (parent plus nested hooks). Nested paints may change live tiles, but every strike inside that tree reads its actor-tile mod from the frozen frame, not from live tiles after sibling paints. If the target's hp is already at or below zero when the parent strike would land, that strike deals no further damage.

Delay jobs schedule a later fire. The fire row id is the delay job id plus the `#fire` suffix, kind `delay_fire`, and pid equal to the delay job id. A fire lands when the primary cursor equals the delay's `slot` value, after that primary step's nested work and before the next primary. Void delays schedule nothing.

Worked packs under `/app/environment/data/kips/` ship miniature `scn` objects (actors, jobs, hooks, tiles) plus a short blurb. Ladder arms under `/app/environment/data/scn_*.json` and `ladder.toml` exercise the same desk, including `/app/environment/data/scn_base.json` and `/app/environment/data/scn_hold_cross.json`. Job and hook objects use fields such as kind, actor, owner, target, dmg, vs, when, tile, mod, to, slot, and void.

Pack `kip_rank` means equal-init primary ranking with void omission. Ladder arm `nest_chain` means nested reaction order under one parent strike. Ladder arm `void_mid` means void hooks leave no transcript rows. Ladder arm `phase_board` means delayed fires honor slot timing with void delays omitted. Ladder arm `snap_paint` means nested paints must not revise the frozen strike-frame mod. Ladder arm `lethal_cut` means a parent strike deals no damage when the target is already at or below zero hp. Ladder arm `fuse_mix` means the joint nest/void/snap/lethal/delay obligations on one scenario. Ladder arm `sib_veil` means sibling paints under an open parent must not revise later nested strike damage.

## Obligation pins
Transcript checks compare `row_ids` (ordered emitted ids) and `pids` (map from each emitted id to its parent id or null) together with final `actors` and `tiles`.
