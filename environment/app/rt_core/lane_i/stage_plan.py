from __future__ import annotations

from rt_core.lane_e.plan_lane import PlanStore, disk_row, plan_row


def resolve_plan(
    cache: PlanStore,
    ckey: str,
    ctx: dict,
    tenant: str,
    tenant_roots: dict[str, str],
    module_path,
    attach_fn,
) -> tuple[dict, str]:
    mkey = plan_row(ckey, ctx)
    dkey = disk_row(ckey, ctx)
    plan, linked_stat = cache.get(mkey, dkey)
    if plan is None:
        imports = sorted({op["import"] for op in __import__("json").loads(module_path.read_text(encoding="utf-8")).get("ops", [])})
        bound = attach_fn(tenant, tenant_roots, imports)
        plan = {
            "imports": bound.imports,
            "tenant_roots": bound.tenant_roots,
            "captured": bound.captured_tenant,
        }
        cache.put(mkey, dkey, plan)
        linked_stat = "linked_miss"
    return plan, linked_stat
