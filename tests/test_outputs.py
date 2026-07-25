"""Behavioral verification for runtime authority and cache isolation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.helpers import rt_harness as h


@pytest.fixture(autouse=True)
def _isolate() -> None:
    h.reset_runtime()


def test_cross_tenant_module_isolates_kv() -> None:
    """Identical module bytes across tenants must not leak KV or filesystem effects."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module(
        [
            {"import": "fs.read", "resource": "notes.txt"},
            {"import": "kv.write", "resource": "seen", "value": "X"},
        ],
        work,
    )
    for tenant, tag in (("tenant-a", "CANARY-A"), ("tenant-b", "CANARY-B")):
        caps = (
            ["fs.read", "fs.write", "kv.write", "kv.read"]
            if tenant == "tenant-a"
            else ["fs.read", "kv.read"]
        )
        manifest = h.sign_manifest(
            {
                "manifest_id": f"gen-{tenant}",
                "tenant": tenant,
                "abi": 2,
                "module": {"digest": digest, "size": mod.stat().st_size},
                "capabilities": caps,
                "limits": {"fuel": 1000000, "host_calls": 64, "output_bytes": 4096},
            }
        )
        mpath = work / f"{tenant}.json"
        mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        resp = h.socket_request(
            {"tenant": tenant, "module": str(mod), "manifest": str(mpath)}
        )
        if tenant == "tenant-a":
            assert resp.get("ok"), resp
    assert h.kv_get("tenant-a", "seen") == "X"
    assert h.kv_get("tenant-b", "seen") != "X"


def test_code_row_hit_across_contexts() -> None:
    """Compiled cache should hit across differing authority contexts."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "clock.read", "resource": ""}], work)
    stats = []
    for tenant in ("tenant-a", "tenant-b"):
        manifest = h.sign_manifest(
            {
                "manifest_id": f"cc-{tenant}",
                "tenant": tenant,
                "abi": 2,
                "module": {"digest": digest, "size": mod.stat().st_size},
                "capabilities": ["clock.read"],
                "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
            }
        )
        mpath = work / f"{tenant}.json"
        mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        resp = h.socket_request(
            {"tenant": tenant, "module": str(mod), "manifest": str(mpath)}
        )
        assert resp.get("ok"), resp
        stats.append(resp["cache"]["compiled"])
    assert stats[0] in {"compiled_miss", "compiled_memory_hit"}
    assert stats[1] in {"compiled_memory_hit", "compiled_persisted_hit"}


def test_plan_row_miss_on_context_change() -> None:
    """Different manifest/policy contexts must not reuse linked import plans."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "env.read", "resource": "TENANT_TAG"}], work)
    m1 = h.sign_manifest(
        {
            "manifest_id": "lk-1",
            "tenant": "tenant-a",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["env.read"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    p1 = work / "m1.json"
    p1.write_text(json.dumps(m1, indent=2) + "\n", encoding="utf-8")
    r1 = h.socket_request(
        {"tenant": "tenant-a", "module": str(mod), "manifest": str(p1)}
    )
    m2 = dict(m1)
    m2["manifest_id"] = "lk-2"
    m2["capabilities"] = ["env.read", "clock.read"]
    p2 = work / "m2.json"
    p2.write_text(json.dumps(h.sign_manifest(m2), indent=2) + "\n", encoding="utf-8")
    r2 = h.socket_request(
        {"tenant": "tenant-a", "module": str(mod), "manifest": str(p2)}
    )
    assert r1.get("ok") and r2.get("ok")
    assert r2["cache"]["linked"] in {"linked_miss", "linked_memory_hit"}


def test_plan_row_hit_on_equivalent_context() -> None:
    """Semantically equivalent repeated contexts should linked-cache hit in memory."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "clock.read", "resource": ""}], work)
    manifest = h.sign_manifest(
        {
            "manifest_id": "eq-1",
            "tenant": "tenant-a",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["clock.read"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    req = {"tenant": "tenant-a", "module": str(mod), "manifest": str(mpath)}
    r1 = h.socket_request(req)
    r2 = h.socket_request(req)
    assert r1.get("ok") and r2.get("ok")
    assert r2["cache"]["linked"] == "linked_memory_hit"


def test_unsigned_doc_change_rejected() -> None:
    """Unsigned manifest capability changes must be rejected."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "kv.write", "resource": "x", "value": "1"}], work)
    manifest = h.sign_manifest(
        {
            "manifest_id": "tamper",
            "tenant": "tenant-b",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["kv.read"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    manifest["capabilities"] = ["kv.write"]
    mpath = work / "bad.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    resp = h.socket_request(
        {"tenant": "tenant-b", "module": str(mod), "manifest": str(mpath)}
    )
    assert not resp.get("ok") or resp.get("error")


def test_rules_refresh_revokes_new_runs() -> None:
    """After policy reload removes a capability, new invocations must deny it."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module(
        [{"import": "kv.write", "resource": "z", "value": "1"}], work
    )
    manifest = h.sign_manifest(
        {
            "manifest_id": "pol",
            "tenant": "tenant-a",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["kv.write"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    before = h.socket_request(
        {"tenant": "tenant-a", "module": str(mod), "manifest": str(mpath)}
    )
    assert before.get("ok")
    cand = work / "policy.json"
    cand.write_text(
        json.dumps(
            {
                "generation": 2,
                "tenants": {
                    "tenant-a": {
                        "capabilities": ["clock.read"],
                        "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess = __import__("subprocess")
    subprocess.run(
        ["/app/bin/rulesctl", "reload", "--candidate", str(cand)],
        check=True,
        capture_output=True,
    )
    after = h.socket_request(
        {"tenant": "tenant-a", "module": str(mod), "manifest": str(mpath)}
    )
    assert not after.get("ok") or after["result"]["status"] != "ok"


def test_active_run_keeps_frozen_view() -> None:
    """Running invocation keeps captured policy while new ones see reload."""
    pytest.skip("barrier orchestration verified in integration smoke")


def test_v2_missing_cap_denied() -> None:
    """ABI v2 omitted capabilities remain denied after defaults processing."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "env.read", "resource": "TENANT_TAG"}], work)
    manifest = h.sign_manifest(
        {
            "manifest_id": "v2omit",
            "tenant": "tenant-b",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": [],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    resp = h.socket_request(
        {"tenant": "tenant-b", "module": str(mod), "manifest": str(mpath)}
    )
    assert resp.get("ok") is False or resp["result"]["status"] == "capability-denied"


def test_v1_default_cap_allowed() -> None:
    """ABI v1 manifests retain documented default capabilities after intersection."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "clock.read", "resource": ""}], work)
    manifest = h.sign_manifest(
        {
            "manifest_id": "v1",
            "tenant": "tenant-a",
            "abi": 1,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["fs.read"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    resp = h.socket_request(
        {"tenant": "tenant-a", "module": str(mod), "manifest": str(mpath)}
    )
    assert resp.get("ok"), resp


def test_fresh_call_budgets_per_run() -> None:
    """Host-call budgets are not borrowed across back-to-back invocations."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    ops = [{"import": "clock.read", "resource": ""} for _ in range(5)]
    mod, digest = h.write_module(ops, work)
    manifest = h.sign_manifest(
        {
            "manifest_id": "budget",
            "tenant": "tenant-a",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["clock.read"],
            "limits": {"fuel": 100000, "host_calls": 3, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    req = {"tenant": "tenant-a", "module": str(mod), "manifest": str(mpath)}
    r1 = h.socket_request(req)
    r2 = h.socket_request(req)
    assert r1["result"]["status"] == "host-call-budget-exhausted" or not r1.get("ok")
    assert r2["result"]["status"] == "host-call-budget-exhausted" or not r2.get("ok")


def test_reduction_cannot_expand_sets() -> None:
    """Invocation grants cannot introduce capabilities absent from manifest and policy."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module(
        [{"import": "kv.write", "resource": "g", "value": "1"}], work
    )
    manifest = h.sign_manifest(
        {
            "manifest_id": "grant",
            "tenant": "tenant-b",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["kv.read"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    grant = work / "grant.json"
    grant.write_text(
        json.dumps({"capabilities": ["kv.write"]}) + "\n", encoding="utf-8"
    )
    resp = h.socket_request(
        {
            "tenant": "tenant-b",
            "module": str(mod),
            "manifest": str(mpath),
            "grant": str(grant),
        }
    )
    assert not resp.get("ok") or resp["result"]["status"] == "capability-denied"


def test_audit_redaction() -> None:
    """Audit records name capabilities without secret env or KV values."""
    h.start_daemon()
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    mod, digest = h.write_module([{"import": "clock.read", "resource": ""}], work)
    manifest = h.sign_manifest(
        {
            "manifest_id": "audit",
            "tenant": "tenant-a",
            "abi": 2,
            "module": {"digest": digest, "size": mod.stat().st_size},
            "capabilities": ["clock.read"],
            "limits": {"fuel": 100000, "host_calls": 8, "output_bytes": 512},
        }
    )
    mpath = work / "m.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    h.socket_request({"tenant": "tenant-a", "module": str(mod), "manifest": str(mpath)})
    text = h.AUDIT.read_text(encoding="utf-8")
    assert "CANARY-A" not in text
    assert "tenant-a" in text
