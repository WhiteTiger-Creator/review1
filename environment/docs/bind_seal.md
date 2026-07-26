Index and lock bind seal and emit

Bind token

bind_token is the first 12 hex chars of sha256 over edge_digest|overlay_ref|str(reloc_off)

(lowercase hex). The reloc argument must be the dossier reloc_off (logical relocation under the active walk base), not zero and not a raw absolute seek used only for payload open.

Lock overlays

YAML overlays under fixtures/overlays/*.lock.yaml bind each gem_id to a version. Each dossier row must match the overlay named by overlay_ref for that gem, and the version must equal the version decoded from the binary gemindex payload.

Emit / rerun

Driver emit must overwrite /app/output/dossier.json and /app/output/replay.jsonl on every run. Append-on-existing leaves residue and fails rerun byte-identity.

index_crc must be the real gemindex post-header CRC (8 lowercase hex digits), not a zero placeholder.

held_out_violations must be the counted held-out algebra failures (required value 0 on the closed fixture set), not a row-count surrogate.

On split_b, emit must recompute each bind_token from the live dossier reloc_off. A token copied from restart.bin is only valid when that reloc still matches. After a walk-base rebase it must change.
