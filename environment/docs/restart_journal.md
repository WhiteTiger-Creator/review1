Mid-horizon restart journal

Modes

- Default / --mode full runs the full optional-dep activation schedule, then emits dossier plus transcript.
- --mode split_a --cut N activates the first N gems in schedule order (N at least 1 and strictly below row_count), appends journal ops, writes /app/output/restart.bin, and does not emit dossier/transcript yet.
- --mode split_b absorbs /app/output/restart.bin (or --resume PATH), activates the remaining gems, folds dependency-set identity over the full edge set, and emits dossier plus transcript.

split_a then split_b with the same gate/side flag and walk base must agree with a clean full run (dossier and transcript bytes).

Restart image (restart.bin)

Little-endian layout

1. Header (12 bytes) with magic GSJR, u16 version 1, u16 reserved 0, u32 FNV-1a of the body that follows.
2. Body includes
   - u32 walk_base active at checkpoint
   - u8 gate_first (1 for gate-first, 0 for sides-first)
   - u8 pad 0
   - u16 act_done (same value as cut)
   - u16 n_completed
   - seed string (u16 length plus UTF-8 bytes)
   - index_crc string (8 lowercase hex digits)
   - u32 rbase copied from the gemindex header
   - n_completed row records
   - u16 n_pending plus pending gem_id strings (schedule tail)
   - u16 n_ledger plus ledger records plus u32 ledger digest

Row record

For each completed gem, encode

- strings gem_id, ver, edge_digest, overlay_ref, platform, opt_side, bind_token (each as u16 length plus bytes)
- u32 act_ord
- u32 reloc_off as the logical relocation under the checkpoint walk base (poff minus rbase plus walk_base), never the absolute payload seek alone
- u32 poff as the absolute payload offset (retained so resume can rebase)

Ledger records

Each ledger record includes

- u32 op where act is 1, cut is 2, and fold is 3
- u32 seq
- gem_id string (empty for cut/fold)

Ledger digest is FNV-1a 32-bit over the concatenation of the canonical encodings of each ledger record (op, seq, then gem_id string with its length prefix), emitted as a raw u32 in the trailer. Absorb must reject digest mismatches. A positive act_done does not waive ledger validation.

Resume obligations

On split_b

1. Validate header magic/version/body CRC and the ledger digest.
2. Re-check every completed row overlay pin against the live lock overlays.
3. If KW_WALK_BASE is set and differs from the frozen checkpoint walk base, rebase every completed row so reloc_off becomes poff minus rbase plus new_base, and recompute bind_token with the new reloc_off. Pending rows activate under the new base directly.
4. Schedule the pending gem ids with the CLI gate/side flag (not only the frozen checkpoint bit). Completed act_ord values from 0 through act_done-1 stay. Pending continue from act_done.
5. Fold closure_digest over the full edge-digest set with the sorted-identity approach in set_identity.md. Encounter/activation order must not feed the closure body.
6. Emit dossier plus transcript for the merged row list. Emit must recompute bind seals from the live reloc_off rather than trusting a stale restart token when reloc has changed.
