from __future__ import annotations

from pathlib import Path

from rt_core.lane_c.code_lane import CodeStore, code_key


def resolve_code(cache: CodeStore, module_digest: str, abi: str, module_path: Path) -> tuple[bytes, str]:
    ckey = code_key(module_digest, str(abi))
    artifact, compiled_stat = cache.get(ckey)
    if artifact is None:
        artifact = module_path.read_bytes()
        cache.put(ckey, artifact)
        compiled_stat = "compiled_miss"
    return artifact, compiled_stat, ckey
