# Offline Bundler gemindex lock-journal recovery

An offline Bundler-style dependency resolve under `/app/environment` must regenerate a reproducible gem lock-closure after mid-horizon crash recovery. A clean full resolve and a split_a then split_b pair with the same flags must agree. Primary activity is offline package dependency management covering gemindex walk, lock-overlay pins, optional-dep scheduling, journaled activation, restart absorb, and content-addressed sealing. Not a generic data transform. Repair the Ruby modules under `/app/environment` so library-level behavior matches the norms below. CLI wrappers alone are not enough. Static or hand-written `/app/output` files are insufficient. The verifier deletes outputs and reruns `/app/environment/tools/kw_run` (and related modes) through the normal pytest pipeline to regenerate artifacts.

Inputs live under `/app/environment/fixtures/`, `/app/environment/docs/mx_rows.yaml`, `/app/environment/data/extra_mtx.yaml`, and `/app/environment/data/walk_seed.txt`. Drive resolves with `/app/environment/tools/kw_run` using KW_ROOT set to `/app/environment` and KW_OUT set to `/app/output`. `/app/environment/docs/operator_cmds.txt` lists argv forms including split modes, sides-first, resume path, and the optional walk-base override env. Companion docs under `/app/environment/docs/` elaborate examples. The norms below are authoritative. Draft notes such as field_notes_draft.md are non-normative. Offline only with no rubygems.org. Toolchain stages under `/app/environment` must match these norms. Wrapping the driver alone is not enough.

Default mode is full resolve. sides-first reverses gate/side ties (default is gate-first). The walk-base override, if present, stands in for training_walk_base during the walk and for dossier reloc/bind seals. Held-out slice bases stay unchanged. On split_b, that same override also rebases completed rows from the restart image. split_a cut N must satisfy N at least 1 and strictly below row_count. Success exit is 0. A restart image with a corrupted ledger digest must make split_b exit nonzero.

Produced files include `/app/output/dossier.json` and `/app/output/replay.jsonl` on full and split_b, plus `/app/output/restart.bin` on split_a only. After a successful split_a, it is false that `/app/output/dossier.json` exists. Only `/app/output/restart.bin` is written until split_b. A second identical driver run must overwrite dossier and transcript byte-identically.

## Gemindex layout

Binary gemindex magic GIX1, little-endian. Header is 16 bytes with version, record count, reloc base (rbase), and a checksum of all bytes after the header. Each record is 32 bytes with absolute payload offset (poff) and length (plen). Payload bytes are name|version|platform.

Payload open always uses absolute poff (never poff minus rbase plus walk_base as a file seek). Dossier reloc_off equals poff minus rbase plus base_u where base_u is the active walk base. A walk-base increase by delta increases every reloc_off by that delta and refreshes every bind_token. closure_digest, gem identity fields, and act_ord stay unchanged. index_crc is the lowercase 8-digit hex of the header checksum field.

## Digests

Digests go through `/app/environment/tools/hex_dgst` (hex digest of stdin; do not substitute a local Digest library). edge_digest is the first 16 hex chars of hex_dgst over edge|name|ver. closure_digest is the full hex_dgst of the UTF-8 string seed|0|tag1|tag2|... where tag1, tag2, ... are the lexicographically sorted edge digests each separated by the pipe character | (literal middle marker 0 between seed and the first tag). Same seed and gem set keep the same closure under annex permutation, activation-order permutation, walk-base change, and mid-horizon resume. Do not fold overlays or reloc into the closure. bind_token is the first 12 hex chars of hex_dgst over edge_digest|overlay_ref|str(reloc_off) using the dossier logical reloc_off. Emit refreshes binds from the live reloc after any rebase.

## Activation order

Matrix rows list gem_id, platform, priority, opt_class, and overlay_ref. opt_class is the optional-dependency class for that gem and must be either gate or side. Default activation order is ascending priority, then gate before side on ties, then ascending gem_id. sides-first flips only that gate/side key. act_ord is the zero-based index. Dossier opt_side equals the matrix opt_class for the same gem_id.

Lock overlays under `/app/environment/fixtures/overlays/` map name to pins (gem_id to version). Each dossier row must match its overlay_ref pin and the version decoded from the gemindex payload. Pin checks apply on first activation and again on resume. extra_mtx.yaml carries training_walk_base, training_annex_order, and slices (id, walk_base, annex_order). Every held-out slice must decode readable payloads under its walk_base and yield the same closure as training.

## Restart image

Restart image little-endian layout uses a header of 12 bytes with magic GSJR, u16 version 1, u16 reserved 0, and a u32 trailer hash of the body. Body fields include u32 walk base, u8 gate_first (1 for gate-first, 0 for sides-first), u8 pad 0, u16 act_done, u16 n_completed, seed string, index_crc string, u32 rbase, completed row records, pending gem_id strings, then ledger records and a trailing u32 digest. Each completed row encodes, in order, the length-prefixed strings gem_id, ver, edge_digest, overlay_ref, platform, and opt_side, then the three little-endian u32 fields act_ord, reloc_off (logical under the checkpoint walk base), and poff (absolute, retained for rebase), then the length-prefixed string bind_token after those u32 fields. Ledger ops use numeric codes where act is 1, cut is 2, and fold is 3. Each record is u32 op, u32 seq, then gem_id (empty for cut/fold). The trailer digest is the 32-bit hash with offset basis 2166136261 and prime 16777619 over those canonical encodings. Absorb rejects digest mismatches. A positive act_done does not waive validation.

## Split semantics

On split_b, validate header and ledger, re-check overlay pins, rebase completed rows under a differing walk-base override, schedule pending gem ids with the CLI gate/side flag, keep completed act_ord values from 0 through act_done-1 and continue pending from act_done, fold closure over the full sorted edge set, and emit dossier and transcript for the merged rows. split_a then split_b with matching gate/side flag and walk base must byte-agree with a clean full run. Gate-first split_a followed by sides-first split_b keeps the completed prefix and reorders only the pending tail.

## Dossier and transcript

Dossier schema field equals gem-shelf-dossier + / + v1. Also emit walk_seed from the seed file, closure_digest (64 hex), index_crc (8 hex, lowercase, non-zero here), rows (objects with gem_id, edge_digest, platform, overlay_ref, act_ord, opt_side, reloc_off, bind_token, ver), and held_out_violations. Every matrix gem appears exactly once. Hex fields are lowercase. Absolute poff is not a dossier field.

Transcript `/app/output/replay.jsonl` has one object per dossier row in act_ord order with gem_id, edge_digest, act_ord, bind_token, overlay_ref, reloc_off, and phase.

Symptoms of partial recovery include a clean full run that can look fine even as checkpoint/resume drifts on reloc seals, closure identity, activation order, or overlay authority. Restart bytes may carry live rows yet mis-seal the ledger trailer that absorb must enforce.

On the closed fixture set held_out_violations reports zero failures.

Transcript phase markers use the lowercase token row.
