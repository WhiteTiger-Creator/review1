# Object-archive link graph

The packing chain is an object-archive pack. Normative target edges:

1. `bag_lib` is a STATIC library with no upstream module deps.
2. `crc_probe` is a STATIC helper. It may exist in the tree for tooling, but it must not appear on the PUBLIC or INTERFACE edge of `dig_fold`, `pol_gate`, `io_glue`, `wal_io`, `obj_stage`, `ix_pack`, `era_clk`, `layer_emit`, or `yseal`.
3. `mtime_hint` is a STATIC helper for tooling clocks only. It must not appear on the PUBLIC or INTERFACE edge of packing or seal targets.
4. `obj_stage` PUBLIC-links only `bag_lib`.
5. `ix_pack` PUBLIC-links only `bag_lib`.
6. `dig_fold` PUBLIC-links only `bag_lib`.
7. `pol_gate` has no library link line beyond its own sources.
8. `wal_io` PUBLIC-links only `bag_lib`.
9. `era_clk` PUBLIC-links only `bag_lib`.
10. `io_glue` PUBLIC-links `bag_lib`, `era_clk`, `dig_fold`, `wal_io`, `pol_gate`, `obj_stage`, and `ix_pack`.
11. `layer_emit` PRIVATE-links only `io_glue`.
12. `yseal` PRIVATE-links only `io_glue`.

INTERFACE compile definitions and forced includes that ship with `crc_probe` must not reach packing or seal translation units. A consumer that PUBLIC-links `crc_probe` inherits those definitions and corrupts artifact provenance for digests, class selection, staging, archive index, generation refresh, journal CRC, and carry or fence bookkeeping.

Pack configure helpers under `/app/environment/mk/host.cmake`, `/app/environment/src/lib_wire.cmake`, and `/app/environment/bx/bin_wire.cmake` must encode the edges above. They must not inject `XP_SIDE`, `XP_OPEN`, or `XP_PAD` compile definitions into the whole project. Those macros are tooling-only and belong solely to consumers that intentionally link `crc_probe`.

Incremental rebuild: `/app/environment/tools/rebuild_emit.sh` configures and builds under `/app/environment/build`. `/app/environment/tools/run_emit_chain.sh` rebuilds, runs `layer_emit`, then runs `yseal`. Generation budget changes must rewrite `/app/environment/var/gen.stamp`, rewrite `/app/environment/var/arc.fence`, rewrite `/app/environment/var/ar.index`, and force sealed artifacts to match the newer budget.

Artifact provenance: unit digests, index digests, and probe sums bind live unit bytes under `/app/environment/data/units/` in manifest order. `/app/environment/var/object_cache/` and `/app/environment/data/shadow_feed.jsonl` are non-authoritative decoys for packing and recovery. Fence `digest` stores `index_hex`.
