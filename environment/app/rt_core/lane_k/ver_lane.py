from __future__ import annotations

V1_DEFAULTS = {"env.read", "clock.read"}
V2_DEFAULTS: set[str] = set()


def expand_decl(version: int, declared: set[str]) -> set[str]:
    if version == 1:
        return set(declared) | V1_DEFAULTS
    return set(declared) | V1_DEFAULTS | V2_DEFAULTS
