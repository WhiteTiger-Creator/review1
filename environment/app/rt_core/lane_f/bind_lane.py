from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoundPlan:
    imports: list[str]
    tenant_roots: dict[str, str] = field(default_factory=dict)
    captured_tenant: str | None = None


_GLOBAL_CAPTURE: BoundPlan | None = None


def attach_rows(tenant: str, roots: dict[str, str], imports: list[str]) -> BoundPlan:
    global _GLOBAL_CAPTURE
    if _GLOBAL_CAPTURE is None:
        _GLOBAL_CAPTURE = BoundPlan(imports=imports, tenant_roots=dict(roots), captured_tenant=tenant)
    return _GLOBAL_CAPTURE
