from __future__ import annotations

from rt_core.lane_f.bind_lane import attach_rows
from rt_core.lane_h.budget_lane import budget_row


def build_runtime_state(tenant: str, tenant_roots: dict[str, str], imports: list[str], limits: dict, effective: set[str]) -> dict:
    bound = attach_rows(tenant, tenant_roots, imports)
    meter = budget_row(limits)
    return {
        "tenant": bound.captured_tenant or tenant,
        "tenant_roots": bound.tenant_roots,
        "roots": bound.tenant_roots,
        "caps": effective,
        "meter": meter,
        "bound": bound,
    }
