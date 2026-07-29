"""Verifier-owned checkpoint v3 parser and mutation helpers."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MAGIC = b"EMCK"
SENTINEL = b'{"sentinel":"unchanged"}\n'

# Fixed header offsets (little-endian envelope fields 1-7).
OFF_MAGIC = 0
OFF_VERSION = 4
OFF_REQUESTED_MODES = 8
OFF_ITERATIONS = 12
OFF_ACTIVE_DOFS = 16
OFF_LINEAGE_DIGEST = 20
OFF_EDGE_IDENTITY_COUNT = 28
OFF_EDGE_IDENTITIES = 32


def fnv1a64(data: bytes) -> int:
    h = FNV_OFFSET
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return h


def write_sentinel(path: Path) -> None:
    path.write_bytes(SENTINEL)


def sentinel_unchanged(path: Path) -> bool:
    return path.exists() and path.read_bytes() == SENTINEL


def truncate(path: Path, nbytes: int) -> None:
    data = path.read_bytes()
    path.write_bytes(data[: max(0, min(nbytes, len(data)))])


def flip_byte(path: Path, offset: int) -> None:
    data = bytearray(path.read_bytes())
    if not data:
        raise ValueError("checkpoint is empty")
    data[offset % len(data)] ^= 0xFF
    path.write_bytes(data)


def replace_bytes(path: Path, offset: int, replacement: bytes) -> None:
    data = bytearray(path.read_bytes())
    end = offset + len(replacement)
    if end > len(data):
        raise ValueError("replacement exceeds checkpoint length")
    data[offset:end] = replacement
    path.write_bytes(data)


def read_uint32(path: Path, offset: int) -> int:
    return struct.unpack_from("<I", path.read_bytes(), offset)[0]


@dataclass
class RitzVectorRecord:
    offset: int
    length: int
    coefficients: list[float]


@dataclass
class CheckpointEnvelope:
  raw: bytes
  magic: bytes
  version: int
  requested_modes: int
  iterations: int
  active_dofs: int
  lineage_digest: int
  edge_identity_count: int
  edge_identities: list[float]
  edge_identities_offset: int
  ritz_value_count: int
  ritz_values: list[float]
  ritz_values_offset: int
  ritz_vector_count: int
  ritz_vectors: list[RitzVectorRecord]
  ritz_vectors_offset: int
  cache_tag_length: int
  cache_tag: bytes
  cache_tag_offset: int
  checksum: int
  checksum_offset: int
  consumed_entire_file: bool
  offsets: dict[str, int] = field(default_factory=dict)


def parse_checkpoint(path: Path | bytes) -> CheckpointEnvelope:
    raw = path.read_bytes() if isinstance(path, Path) else path
    if len(raw) < OFF_EDGE_IDENTITIES:
        raise ValueError("checkpoint too short for header")

    magic = raw[OFF_MAGIC:OFF_VERSION]
    if magic != MAGIC:
        raise ValueError(f"invalid magic: {magic!r}")

    version = struct.unpack_from("<I", raw, OFF_VERSION)[0]
    requested_modes = struct.unpack_from("<i", raw, OFF_REQUESTED_MODES)[0]
    iterations = struct.unpack_from("<i", raw, OFF_ITERATIONS)[0]
    active_dofs = struct.unpack_from("<i", raw, OFF_ACTIVE_DOFS)[0]
    lineage_digest = struct.unpack_from("<Q", raw, OFF_LINEAGE_DIGEST)[0]
    edge_identity_count = struct.unpack_from("<I", raw, OFF_EDGE_IDENTITY_COUNT)[0]

    pos = OFF_EDGE_IDENTITIES
    edge_identities_offset = pos
    need = pos + 8 * edge_identity_count
    if len(raw) < need:
        raise ValueError("truncated edge_identities")
    edge_identities = list(
        struct.unpack_from(f"<{edge_identity_count}d", raw, pos) if edge_identity_count else ()
    )
    pos = need

    if len(raw) < pos + 4:
        raise ValueError("truncated ritz_value_count")
    ritz_value_count = struct.unpack_from("<I", raw, pos)[0]
    pos += 4
    ritz_values_offset = pos
    need = pos + 8 * ritz_value_count
    if len(raw) < need:
        raise ValueError("truncated ritz_values")
    ritz_values = list(struct.unpack_from(f"<{ritz_value_count}d", raw, pos) if ritz_value_count else ())
    pos = need

    if len(raw) < pos + 4:
        raise ValueError("truncated ritz_vector_count")
    ritz_vector_count = struct.unpack_from("<I", raw, pos)[0]
    pos += 4
    ritz_vectors_offset = pos
    ritz_vectors: list[RitzVectorRecord] = []
    for _ in range(ritz_vector_count):
        if len(raw) < pos + 4:
            raise ValueError("truncated ritz vector length")
        voff = pos
        vlen = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        need = pos + 8 * vlen
        if len(raw) < need:
            raise ValueError("truncated ritz vector coefficients")
        coeffs = list(struct.unpack_from(f"<{vlen}d", raw, pos))
        pos = need
        ritz_vectors.append(RitzVectorRecord(offset=voff, length=vlen, coefficients=coeffs))

    if len(raw) < pos + 4:
        raise ValueError("truncated cache_tag_length")
    cache_tag_offset = pos
    cache_tag_length = struct.unpack_from("<I", raw, pos)[0]
    pos += 4
    need = pos + cache_tag_length
    if len(raw) < need:
        raise ValueError("truncated cache_tag")
    cache_tag = raw[pos : pos + cache_tag_length]
    pos = need

    if len(raw) < pos + 8:
        raise ValueError("truncated checksum")
    checksum_offset = pos
    checksum = struct.unpack_from("<Q", raw, pos)[0]
    pos += 8

    consumed = pos == len(raw)
    offsets = {
        "magic": OFF_MAGIC,
        "version": OFF_VERSION,
        "requested_modes": OFF_REQUESTED_MODES,
        "iterations": OFF_ITERATIONS,
        "active_dofs": OFF_ACTIVE_DOFS,
        "lineage_digest": OFF_LINEAGE_DIGEST,
        "edge_identity_count": OFF_EDGE_IDENTITY_COUNT,
        "edge_identities": edge_identities_offset,
        "ritz_value_count": ritz_values_offset - 4,
        "ritz_values": ritz_values_offset,
        "ritz_vector_count": ritz_vectors_offset - 4,
        "ritz_vectors": ritz_vectors_offset,
        "cache_tag_length": cache_tag_offset,
        "cache_tag": cache_tag_offset + 4,
        "checksum": checksum_offset,
    }

    return CheckpointEnvelope(
        raw=raw,
        magic=magic,
        version=version,
        requested_modes=requested_modes,
        iterations=iterations,
        active_dofs=active_dofs,
        lineage_digest=lineage_digest,
        edge_identity_count=edge_identity_count,
        edge_identities=edge_identities,
        edge_identities_offset=edge_identities_offset,
        ritz_value_count=ritz_value_count,
        ritz_values=ritz_values,
        ritz_values_offset=ritz_values_offset,
        ritz_vector_count=ritz_vector_count,
        ritz_vectors=ritz_vectors,
        ritz_vectors_offset=ritz_vectors_offset,
        cache_tag_length=cache_tag_length,
        cache_tag=cache_tag,
        cache_tag_offset=cache_tag_offset,
        checksum=checksum,
        checksum_offset=checksum_offset,
        consumed_entire_file=consumed,
        offsets=offsets,
    )


def edge_identities_bytes(edge_identities: list[float]) -> bytes:
    return struct.pack(f"<{len(edge_identities)}d", *edge_identities) if edge_identities else b""


def recompute_lineage_digest(edge_identities: list[float]) -> int:
    return fnv1a64(edge_identities_bytes(edge_identities))


def recompute_checksum(prefix: bytes) -> int:
    return fnv1a64(prefix)


def serialize_checkpoint(
    *,
    requested_modes: int,
    iterations: int,
    active_dofs: int,
    edge_identities: list[float],
    ritz_values: list[float],
    ritz_vectors: list[list[float]],
    cache_tag: bytes,
) -> bytes:
    edge_identity_count = len(edge_identities)
    lineage = recompute_lineage_digest(edge_identities)

    body = bytearray()
    body += MAGIC
    body += struct.pack("<I", 3)
    body += struct.pack("<i", requested_modes)
    body += struct.pack("<i", iterations)
    body += struct.pack("<i", active_dofs)
    body += struct.pack("<Q", lineage)
    body += struct.pack("<I", edge_identity_count)
    body += edge_identities_bytes(edge_identities)
    body += struct.pack("<I", len(ritz_values))
    if ritz_values:
        body += struct.pack(f"<{len(ritz_values)}d", *ritz_values)
    body += struct.pack("<I", len(ritz_vectors))
    for vec in ritz_vectors:
        body += struct.pack("<I", len(vec))
        if vec:
            body += struct.pack(f"<{len(vec)}d", *vec)
    body += struct.pack("<I", len(cache_tag))
    body += cache_tag
    checksum = recompute_checksum(bytes(body))
    body += struct.pack("<Q", checksum)
    return bytes(body)


def rewrite_with_updates(path: Path, **updates: object) -> None:
    env = parse_checkpoint(path)
    edge_identities = list(updates.get("edge_identities", env.edge_identities))  # type: ignore[arg-type]
    ritz_values = list(updates.get("ritz_values", env.ritz_values))  # type: ignore[arg-type]
    ritz_vectors = [list(v.coefficients) for v in env.ritz_vectors]
    if "ritz_vectors" in updates:
        ritz_vectors = list(updates["ritz_vectors"])  # type: ignore[assignment]
    cache_tag = updates.get("cache_tag", env.cache_tag)  # type: ignore[assignment]
    if isinstance(cache_tag, str):
        cache_tag = cache_tag.encode()
    data = serialize_checkpoint(
        requested_modes=int(updates.get("requested_modes", env.requested_modes)),
        iterations=int(updates.get("iterations", env.iterations)),
        active_dofs=int(updates.get("active_dofs", env.active_dofs)),
        edge_identities=[float(x) for x in edge_identities],
        ritz_values=[float(x) for x in ritz_values],
        ritz_vectors=ritz_vectors,
        cache_tag=bytes(cache_tag),
    )
    path.write_bytes(data)


def patch_field(path: Path, offset: int, replacement: bytes, *, recompute_checksum: bool = True) -> None:
    data = bytearray(path.read_bytes())
    end = offset + len(replacement)
    if end > len(data):
        raise ValueError("patch exceeds file length")
    data[offset:end] = replacement
    if recompute_checksum and len(data) >= 8:
        checksum_offset = len(data) - 8
        struct.pack_into("<Q", data, checksum_offset, fnv1a64(bytes(data[:checksum_offset])))
    path.write_bytes(data)


def patch_lineage_and_checksum(path: Path) -> None:
    env = parse_checkpoint(path)
    edge_bytes = edge_identities_bytes(env.edge_identities)
    lineage = fnv1a64(edge_bytes)
    data = bytearray(path.read_bytes())
    struct.pack_into("<Q", data, OFF_LINEAGE_DIGEST, lineage)
    checksum = fnv1a64(bytes(data[: env.checksum_offset]))
    struct.pack_into("<Q", data, env.checksum_offset, checksum)
    path.write_bytes(data)


def hash_to_identity_double(key: str) -> float:
    bits = fnv1a64(key.encode())
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def expected_edge_identities(mesh_path: Path) -> list[float]:
    """Recompute field-8 identities using the public checkpoint encoding algorithm."""
    from helpers.reference_nedelec import build_canonical_topology, parse_mesh_file

    topo = build_canonical_topology(parse_mesh_file(mesh_path))
    out: list[float] = []

    def fmt(v: float) -> str:
        return format(float(v), ".17g")

    for gid in topo.reduced_to_global:
        lo, hi = topo.edge_keys[gid]
        key = (
            f"{fmt(lo[0])} {fmt(lo[1])} {fmt(lo[2])}|"
            f"{fmt(hi[0])} {fmt(hi[1])} {fmt(hi[2])}"
        )
        out.append(hash_to_identity_double(key))
    return out
