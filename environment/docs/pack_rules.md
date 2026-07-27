# Mesh Span Rules

The public command is `/app/environment/tools/run_emit_chain.sh`. It rebuilds the CMake object-archive pack into `/app/environment/build/cmd/xbin/layer_emit` and `/app/environment/build/cmd/yseal`, then writes `/app/output/span.journal` and `/app/output/span_transcript.json`. Target edges and INTERFACE pollution rules are normative in `/app/environment/docs/link_graph.md`.

Units live under `/app/environment/data/units/` as `u0.bin`, `u1.bin`, and `u2.bin`. `/app/environment/data/order_list.toml` lists the manifest order as `order = ["u0.bin", "u1.bin", "u2.bin"]`. `/app/environment/data/ref_h0.toml` contains `pair_ref = "h0"`.

Object staging: packing must select unit payloads by content identity against the live tree. `/app/environment/var/object_cache/` may hold decoy blobs. A cache blob is never selected when its bytes differ from the live unit of the same name. File modification times must not override a content mismatch.

Archive index: after units are selected, emit writes `/app/environment/var/ar.index`. Each line is `name content_hex gen` where `content_hex` is a 32-bit FNV-1a over that unit's raw bytes printed as 16 lowercase hex, and `gen` is the active generation as a decimal integer. Lines follow manifest order and are joined with a single newline between lines (no trailing newline inside the hash input). `index_hex` is a 32-bit FNV-1a over the ASCII bytes of that joined body, printed as 16 lowercase hex. The on-disk file may end with a trailing newline after the body.

`/app/environment/data/gen_limit.toml` contains one integer entry, `gen_epoch = N`. `/app/environment/var/gen.stamp` is a single decimal integer line. Before refreshing generation, callers must read the stamp value that is already on disk. After loading a span, the active generation is the newer value when the budget is greater than the stamp, and the stamp file is rewritten to match that active value. The sealed record's `gen_epoch` and the transcript's `stamp_epoch` must both equal that active value after refresh. A stale stamp never overrides a higher budget.

`probe_sum` is computed as the sum of the first little-endian float32 stored in each selected unit, in manifest order. Numeric comparisons use absolute tolerance `1e-5`.

`unit_digest` is a 32-bit FNV-1a value over these bytes in order: the concatenated raw unit bytes in manifest order, then the active generation as four little-endian bytes, then `unit_count` as four little-endian bytes, then the ASCII bytes of `index_hex`. It is formatted as a zero-padded 16-character lowercase hex string. Extra bytes injected by tooling headers must not enter this hash.

`mesh_id` is computed as a 32-bit FNV-1a value over the ASCII bytes of `unit_digest` followed by the ASCII bytes of `pair_ref`. It is formatted as a zero-padded 16-character lowercase hex string. Extra bytes injected by tooling headers must not enter this hash.

`seal_class` is set to `mesh_open_t` only when the last hex nibble of `unit_digest` is odd and `gen_epoch == stamp_epoch`. Otherwise it is set to `mesh_hold_t`. The class names also appear in `/app/environment/src/pol_gate/policy/pack_role.te`.

`unit_count` equals the number of unit files listed in the manifest order.

`index_hex` appears on the transcript. It must equal the archive-index digest defined above for the selected units and active generation.

`carry_hex` is an 8-character lowercase hex string on the transcript only (not stored inside the journal body). Emit resolves it before overwriting the journal and writes the value to `/app/environment/var/carry.side` as a single line of 8 lowercase hex digits. `yseal` copies that file into the transcript field.

Carry is non-zero only when all of the following hold after reading the pre-refresh stamp and computing the active generation:

1. The active generation is not strictly greater than the pre-refresh stamp.
2. `/app/output/span.journal` already exists and unpacks cleanly.
3. That journal's `gen_epoch` equals the active generation.
4. `/app/environment/var/arc.fence` exists, its `gen` equals the active generation, and its `digest` equals the `index_hex` recomputed from the journal's embedded unit blobs at that generation.

When those hold, `carry_hex` is the prior record's `wal_crc` formatted as 8 lowercase hex digits. Otherwise `carry_hex` is `00000000`, including generation advances, gen-mismatched journals, and fence lines that are missing, stale, or disagree with the recomputed index digest.

A second emit at the same active generation after a unit payload change must still carry the prior `wal_crc` when the fence was rewritten correctly on the first emit and the index digest advanced with the payload. Torn-journal recovery that rebuilds from live units after a generation advance must rewrite `carry.side` to `00000000`.

`span_tag` is an 8-character lowercase hex string on the transcript. It is a 32-bit FNV-1a over the ASCII bytes of `unit_digest`, then the ASCII bytes of `carry_hex`, then the active generation as four little-endian bytes, printed as zero-padded 8 lowercase hex digits.

`/app/environment/var/arc.fence` is a single text line `gen=<int> digest=<16 lowercase hex>`. The `digest` field stores `index_hex`, not `unit_digest`. After a successful emit, and after torn-journal recovery that rewrites the journal, it must be rewritten to the active generation and the live `index_hex`. Seal and torn-journal recovery must treat the fence as authoritative for whether cached blobs may be consulted: if the fence generation does not equal the active generation, or the journal CRC/trailer is invalid, recovery uses live units under `/app/environment/data/units/` only. Cache blobs are never selected merely because a fence line exists on disk.

The journal uses little-endian `SPJ2` layout:

1. 4 bytes magic, `SPJ2`
2. int32 `gen_epoch`
3. int32 `unit_count`
4. for each unit in manifest order: int32 `nbytes`, then `nbytes` raw bytes
5. float32 `probe_sum`
6. 16 ASCII bytes `unit_digest`
7. 16 NUL-padded bytes `pair_ref`
8. uint32 `wal_crc`
9. int32 `trailer_gen`

`wal_crc` is computed as CRC-32/ISO-HDLC with polynomial `0xEDB88320`, init `0xFFFFFFFF`, and xorout `0xFFFFFFFF`, over all bytes after magic through the end of the padded pair reference. It excludes the CRC field and trailer. `trailer_gen` must equal `gen_epoch`.

`/app/environment/data/shadow_feed.jsonl` and `/app/environment/var/object_cache/` are non-authoritative. Cache decoys may carry marker suffixes such as `-stale-cache-pad` and must still lose to live bytes on content mismatch. When cache blobs differ from live units, the absolute difference between the live `probe_sum` and a probe sum computed from the cache tree must exceed `1.0`. Verifier cache-poison fixtures begin each decoy blob with little-endian float32 `99.0`. If the journal CRC or trailer is invalid, `yseal` reconstructs from live units under `/app/environment/data/units/` and the current generation rules, then rewrites the journal, fence, and archive index. Cache blobs are never a recovery source when the fence generation disagrees with the active generation, must not be selected merely because a fence line exists on disk, and must not be used in place of live units for digest, index, or probe calculation.

`layer_emit` accepts `--pair` and `--journal`. `yseal` accepts `--journal` and `--report`. Direct seal checks may invoke `/app/environment/build/cmd/yseal/yseal --journal /app/output/span.journal --report /app/output/span_transcript.json`.
