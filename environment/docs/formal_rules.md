Formal rules for offline Bundler gemindex lock-journal recovery

These norms define the offline package dependency resolve contract covering gemindex walk, lock-overlay binding, optional-dep activation, mid-horizon journal restart, and content-addressed resolve provenance. They are not a general data-transform recipe.

Precedence (normative mesh)

When documents disagree, apply this order with highest first.

1. docs/formal_rules.md (this file)
2. docs/walk_reloc.md
3. docs/set_identity.md
4. docs/opt_schedule.md
5. docs/bind_seal.md
6. docs/restart_journal.md
7. docs/mx_rows.yaml, data/extra_mtx.yaml, lock overlays, docs/operator_cmds.txt
8. docs/field_notes_draft.md (non-normative draft only; never overrides items one through seven)

Companion docs supply concrete layout, digest, scheduling, seal, and restart detail. This spine states the coupled properties those details must satisfy together.

CLI

From /app, with KW_ROOT defaulting to /app/environment.

/app/environment/tools/kw_run
/app/environment/tools/kw_run --mode split_a --cut 4
/app/environment/tools/kw_run --mode split_b

Optional flag --sides-first flips gate-first optional-dependency activation (default is gate-first). Optional env KW_WALK_BASE overrides training_walk_base for the resolve walk (see operator_cmds.txt). Lock-closure artifacts must be produced by this resolve driver. Static writes that skip the driver fail.

Outputs include
- /app/output/dossier.json for the resolve dossier / lock-closure (full and split_b)
- /app/output/replay.jsonl for the optional-dep activation transcript (full and split_b)
- /app/output/restart.bin for the mid-horizon restart image (split_a only)

Coupled properties (must hold simultaneously)

1. Absolute payload open, logical reloc seal. Payload bytes are always read at the absolute file offset stored in the gemindex record. Dossier reloc_off is the logical relocation under the active walk base (detail in walk_reloc.md). These two quantities are not interchangeable when the walk base differs from the header reloc base.
2. Dependency-set identity is walk-order free. closure_digest depends on the walk seed and the sorted edge-digest set only (set_identity.md). Permuting first-walk annex order, changing the walk base, or changing activation order must not change closure_digest for the same gem dependency set.
3. Bind seal tracks reloc. bind_token seals edge_digest, overlay_ref, and the dossier reloc_off together (bind_seal.md). A walk-base change that shifts every reloc_off by a constant must shift every bind_token accordingly while leaving closure_digest and gem identity fields unchanged.
4. Index and lock pin. Each dossier row matches its lock overlay pin and the version decoded from the gemindex payload. Pin checks apply on first activation and again on resume absorb.
5. Held-out resolve algebra. Every slice in data/extra_mtx.yaml must resolve readable payloads under its walk_base and yield the same closure as training. held_out_violations must be zero.
6. Rerun overwrite. A second driver run must leave dossier and transcript byte-identical (no append residue).
7. Coverage. Every matrix gem appears exactly once with no extras.
8. Mid-horizon agreement. For the same seed, walk base, and gate/side flag, a clean full resolve must byte-agree with split_a (cut in 1 through n-1) followed by split_b on the resulting restart.bin, for dossier.json and replay.jsonl. Restart layout and ledger norms are in restart_journal.md.
9. Resume rebasing. When split_b runs under a KW_WALK_BASE that differs from the walk base frozen in restart.bin, every completed and pending row must expose reloc_off / bind_token under the new base. Closure identity and gem identity fields stay stable.

Resolve dossier schema gem-shelf-dossier/v1 fields include schema, walk_seed, closure_digest, index_crc, rows, and held_out_violations. Each row carries gem_id, edge_digest, platform, overlay_ref, act_ord, opt_side, reloc_off, bind_token, and ver.

Activation transcript replay.jsonl has one JSON object per dossier row in the same act_ord order with phase, gem_id, edge_digest, act_ord, bind_token, overlay_ref, and reloc_off.
