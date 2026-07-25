from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from rt_core.lane_b.doc_lane import check_doc
from rt_core.lane_c.code_lane import CodeStore
from rt_core.lane_e.plan_lane import PlanStore
from rt_core.lane_i.stage_bind import build_runtime_state
from rt_core.lane_i.stage_code import resolve_code
from rt_core.lane_i.stage_plan import resolve_plan
from rt_core.lane_i.stage_snap import ensure_book, tenant_view
from rt_core.lane_i.stage_ver import resolve_caps, resolve_limits
from rt_core.lane_j.audit import write_audit
from rt_core.lane_m.imports import run_import
from rt_core.errors import HostError
from rt_core.lane_f.bind_lane import attach_rows


_COMPILED: CodeStore | None = None
_LINKED: PlanStore | None = None


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module_ops(path: Path) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return list(doc.get("ops", []))


def run_invocation(req: dict, cfg: Path, state_dir: str) -> dict:
    global _COMPILED, _LINKED
    ensure_book()
    if _COMPILED is None:
        _COMPILED = CodeStore(Path(state_dir) / "cache" / "compiled")
    if _LINKED is None:
        _LINKED = PlanStore(Path(state_dir) / "cache" / "linked")

    tenant = req["tenant"]
    module_path = Path(req["module"])
    manifest_path = Path(req["manifest"])
    grant_path = Path(req["grant"]) if req.get("grant") else None
    trust = Path("/data/trust")
    module_digest = _digest_file(module_path)
    try:
        manifest = check_doc(manifest_path, trust)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if manifest.get("tenant") != tenant:
        return {"ok": False, "error": "tenant-mismatch"}
    if manifest.get("module", {}).get("digest") != module_digest:
        return {"ok": False, "error": "module-digest-mismatch"}
    grant = {}
    if grant_path is not None and grant_path.is_file():
        grant = json.loads(grant_path.read_text(encoding="utf-8"))
    abi = int(manifest.get("abi", 2))
    policy_view = tenant_view(tenant)
    effective = resolve_caps(abi, manifest, policy_view, grant)
    limits = resolve_limits(manifest, policy_view, grant)
    ctx = {
        "tenant": tenant,
        "abi": str(abi),
        "manifest_digest": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16],
        "policy_digest": policy_view.get("digest", ""),
        "grant_digest": hashlib.sha256(json.dumps(grant, sort_keys=True).encode()).hexdigest()[:16] if grant else "",
    }
    _, compiled_stat, ckey = resolve_code(_COMPILED, module_digest, str(abi), module_path)
    tenant_roots = {tenant: f"/data/tenants/{tenant}"}
    plan, linked_stat = resolve_plan(
        _LINKED, ckey, ctx, tenant, tenant_roots, module_path, attach_rows
    )
    imports = sorted({op["import"] for op in _load_module_ops(module_path)})
    state = build_runtime_state(tenant, plan.get("tenant_roots", tenant_roots), imports, limits, effective)
    state["tenant"] = plan.get("captured") or tenant
    meter = state["meter"]
    outputs: list[str] = []
    status = "ok"
    try:
        for op in _load_module_ops(module_path):
            if op.get("import") == "barrier":
                gate = Path(f"/app/state/gates/{tenant}-{op.get('resource','default')}.pipe")
                gate.parent.mkdir(parents=True, exist_ok=True)
                if not gate.exists():
                    os.mkfifo(str(gate))
                with open(gate, "r", encoding="utf-8") as fh:
                    fh.read()
                continue
            result = run_import(
                op["import"],
                op.get("resource", ""),
                state,
                op.get("value"),
            )
            outputs.append(result)
    except HostError as exc:
        status = exc.code
    rid = req.get("request_id") or str(uuid.uuid4())
    out_dir = Path("/output/rt-runs") / rid
    out_dir.mkdir(parents=True, exist_ok=True)
    result_doc = {
        "ok": status == "ok",
        "request_id": rid,
        "tenant": tenant,
        "module_digest": module_digest,
        "manifest_digest": ctx["manifest_digest"],
        "policy_digest": ctx["policy_digest"],
        "grant_digest": ctx["grant_digest"],
        "abi": abi,
        "cache": {
            "compiled": compiled_stat,
            "linked": linked_stat,
        },
        "effective_caps": sorted(effective),
        "budgets": {
            "fuel_remaining": meter.fuel,
            "host_calls_remaining": meter.host_calls,
            "output_bytes_remaining": meter.output_bytes,
        },
        "result": {"status": status, "outputs": outputs},
    }
    (out_dir / "result.json").write_text(json.dumps(result_doc, indent=2) + "\n", encoding="utf-8")
    write_audit(result_doc)
    return {"ok": status == "ok", "request_id": rid, "result": result_doc["result"], "cache": result_doc["cache"]}
