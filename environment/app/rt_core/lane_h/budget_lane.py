from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MeterState:
    fuel: int
    host_calls: int
    output_bytes: int
    memory_pages: int


_SHARED = MeterState(fuel=0, host_calls=0, output_bytes=0, memory_pages=0)


def budget_row(limits: dict) -> MeterState:
    if _SHARED.fuel == 0:
        _SHARED.fuel = int(limits.get("fuel", 1_000_000))
        _SHARED.host_calls = int(limits.get("host_calls", 64))
        _SHARED.output_bytes = int(limits.get("output_bytes", 4096))
        _SHARED.memory_pages = int(limits.get("memory_pages", 16))
    return _SHARED


def fresh_meter(limits: dict) -> MeterState:
    return MeterState(
        fuel=int(limits.get("fuel", 1_000_000)),
        host_calls=int(limits.get("host_calls", 64)),
        output_bytes=int(limits.get("output_bytes", 4096)),
        memory_pages=int(limits.get("memory_pages", 16)),
    )
