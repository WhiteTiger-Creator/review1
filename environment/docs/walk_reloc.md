Gemindex walk and relocation

Binary gemindex (fixtures/ix_blob.bin)

Bundler-style installed gemindex header (16 bytes, little-endian)

- magic GIX1
- u16 version
- u16 record count
- u32 reloc base
- u32 CRC32 of all bytes after the header

Each record is 32 bytes covering name hash, version tag, platform bits, payload offset, payload length, flags, edge tag, reserved.

Payload bytes are name|version|platform.

Absolute open vs logical reloc

Stored payload offsets are absolute file offsets. Reading a record under any walk base base_u must open the payload at that absolute file offset (never payload_offset minus reloc_base plus base_u as a file seek).

The dossier field reloc_off is the logical dependency relocation

reloc_off is payload_offset minus reloc_base plus base_u

where base_u is the active resolve walk base (training_walk_base, or KW_WALK_BASE when set).

If the active walk base increases by an integer delta, every dossier reloc_off increases by exactly that delta (reloc_off plus delta under the probed base). Every bind_token must be recomputed with the new reloc_off. closure_digest, gem identity fields (gem_id, ver, edge_digest, platform, overlay_ref), and act_ord stay unchanged.

index_crc in the dossier is the lowercase 8-digit hex of the header CRC32 field (CRC of the post-header bytes).

When base_u equals the header reloc base, reloc_off numerically equals the absolute payload offset. That coincidence must not be treated as a definition. Held-out slices and KW_WALK_BASE probes use other bases, and only the absolute-open approach keeps payloads readable there.
