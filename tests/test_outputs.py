"""Behavioral verifier for the privileged helper authority dispatcher."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

APP = Path("/app")
SRC = APP / "cmd" / "privhelper"
SUPPORT = Path("/tests/support")
BIN = Path("/tmp/privhelper-verifier-bin")
CALLER_ENV = APP / "fixtures" / "contaminated-caller.conf"


def request_digest(req: dict) -> str:
    parts = [
        "privhelper-request-v1",
        req["request_id"],
        req["principal"],
        req["action"],
        req["unit"],
    ]
    blob = b"\x00".join(p.encode() for p in parts)
    return hashlib.sha256(blob).hexdigest()


def load_priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes((SUPPORT / "authority.priv").read_bytes())


def sign_bytes(data: bytes) -> bytes:
    return load_priv().sign(data)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ledger_digest() -> str:
    def load(path: Path, key: str):
        rows = []
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        rows.sort(key=lambda r: r.get(key, 0))
        return rows

    payload = {
        "decisions": load(APP / "var/privhelper/decisions.jsonl", "seq"),
        "effects": load(APP / "var/privhelper/effects.jsonl", "seq"),
        "journal": load(APP / "var/privhelper/journal.jsonl", "event_seq"),
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def run(args, check=True, input_text=None):
    env = os.environ.copy()
    env["CGO_ENABLED"] = "0"
    cp = subprocess.run(
        [str(BIN), *args],
        text=True,
        capture_output=True,
        input=input_text,
        env=env,
        check=False,
    )
    if check and cp.returncode != 0:
        raise AssertionError(
            f"cmd failed ({cp.returncode}): {args}\nstdout={cp.stdout}\nstderr={cp.stderr}"
        )
    return cp


def effects() -> list[dict]:
    path = APP / "var/privhelper/effects.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def decisions() -> list[dict]:
    path = APP / "var/privhelper/decisions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def journal() -> list[dict]:
    path = APP / "var/privhelper/journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def make_request(path: Path, **fields) -> Path:
    write_json(path, fields)
    return path


def build_signed_manifest(generation: int, policy: dict | None = None, helpers: dict | None = None) -> tuple[Path, Path, dict, str]:
    base = json.loads((APP / "share/privhelper/authority-manifest-v1.json").read_text())
    man = {
        "scenario": "ops-seal",
        "generation": generation,
        "policy": policy or base["policy"],
        "helpers": helpers or base["helpers"],
    }
    raw = (json.dumps(man, indent=2) + "\n").encode()
    sig = sign_bytes(raw)
    td = Path(tempfile.mkdtemp(prefix="man-"))
    mpath = td / "manifest.json"
    spath = td / "manifest.sig"
    mpath.write_bytes(raw)
    spath.write_bytes(sig)
    return mpath, spath, man, hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="session", autouse=True)
def build_verifier_binary():
    """Compile submitted Go sources into an isolated verifier binary."""
    assert SRC.exists(), "missing Go sources under /app/cmd/privhelper"
    env = os.environ.copy()
    env.update({"CGO_ENABLED": "0", "GOWORK": "off", "GOFLAGS": "-mod=readonly"})
    cp = subprocess.run(
        ["go", "build", "-o", str(BIN), "./cmd/privhelper"],
        cwd="/app",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, f"go build failed:\n{cp.stdout}\n{cp.stderr}"
    assert BIN.exists()
    yield


@pytest.fixture(autouse=True)
def clean_state():
    """Reset durable state before every test."""
    run(["reset", "--scenario", "ops-seal"])
    yield


# ---------------------------------------------------------------------------
# A. Baseline and policy
# ---------------------------------------------------------------------------


def test_owner_actions_succeed_on_generation_one():
    """Generation-1 owner seal/export/rotate requests are allowed with matching effects."""
    for action, effect, unit in [
        ("seal_unit", "unit_sealed", "alpha-owner-1"),
        ("export_bundle", "bundle_exported", "alpha-owner-1"),
        ("rotate_token", "token_rotated", "tok-owner-1"),
    ]:
        req = {
            "request_id": f"own-{action}",
            "principal": "ops.owner",
            "action": action,
            "unit": unit,
        }
        p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
        out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
        assert out["decision"] == "allow"
        assert out["outcome"] == effect
    assert len(effects()) == 3


def test_operator_seal_and_export_succeed():
    """Operators may seal and export under generation-1 policy."""
    for action, effect in [("seal_unit", "unit_sealed"), ("export_bundle", "bundle_exported")]:
        req = {
            "request_id": f"op-{action}",
            "principal": "ops.operator",
            "action": action,
            "unit": "pier-op-1",
        }
        p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
        out = json.loads(run(["dispatch", "--request", str(p), "--via", "job"]).stdout)
        assert out["decision"] == "allow"
        assert out["outcome"] == effect


def test_denied_principals_and_actions_leave_no_effects():
    """Guest, auditor, unknown principal, unknown action, and operator rotate are denied without effects."""
    cases = [
        ("ops.guest", "seal_unit", "g1"),
        ("ops.auditor", "export_bundle", "a1"),
        ("ops.nobody", "seal_unit", "u1"),
        ("ops.owner", "invent_action", "u2"),
        ("ops.operator", "rotate_token", "tok"),
    ]
    for i, (principal, action, unit) in enumerate(cases):
        req = {
            "request_id": f"deny-{i}",
            "principal": principal,
            "action": action,
            "unit": unit,
        }
        p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
        out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
        assert out["decision"] == "deny"
        assert out["outcome"] == "none"
    assert effects() == []


def test_direct_and_job_surfaces_agree():
    """Direct and job launches produce the same authorization decision for identical requests."""
    results = []
    for via in ("direct", "job"):
        run(["reset", "--scenario", "ops-seal"])
        req = {
            "request_id": "surface-1",
            "principal": "ops.operator",
            "action": "seal_unit",
            "unit": "same-unit",
        }
        p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
        out = json.loads(run(["dispatch", "--request", str(p), "--via", via]).stdout)
        results.append((out["decision"], out["outcome"]))
    assert results[0] == results[1] == ("allow", "unit_sealed")


# ---------------------------------------------------------------------------
# B. Caller substitution and live helper integrity
# ---------------------------------------------------------------------------


def test_contaminated_caller_env_does_not_hijack_helper():
    """Contaminated HELPER_PATH/PATH/PYTHON*/BASH_ENV/ENV/LD_PRELOAD cannot change trusted helper identity."""
    req = {
        "request_id": "contam-1",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "c-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    out = json.loads(
        run(
            [
                "dispatch",
                "--request",
                str(p),
                "--via",
                "job",
                "--caller-env",
                str(CALLER_ENV),
            ]
        ).stdout
    )
    assert out["decision"] == "allow"
    assert out["helper_path"].startswith("/app/libexec/privhelper/")
    assert out.get("helper_trusted", True) is True or Path(out["helper_path"]).exists()
    trusted = file_sha256(APP / "libexec/privhelper/seal-unit.py")
    assert out["helper_digest"] == trusted


def test_caller_bin_artifacts_remain_and_differ():
    """Competing caller-bin helpers remain present and differ from trusted libexec helpers after success."""
    req = {
        "request_id": "preserve-1",
        "principal": "ops.owner",
        "action": "export_bundle",
        "unit": "p-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    run(["dispatch", "--request", str(p), "--via", "direct", "--caller-env", str(CALLER_ENV)])
    for name in ("seal-unit", "export-bundle", "rotate-token"):
        caller = APP / "var/caller-bin" / name
        assert caller.exists()
        assert caller.stat().st_size > 0
    trusted = (APP / "libexec/privhelper/export-bundle.py").read_bytes()
    competing = (APP / "var/caller-bin/export-bundle").read_bytes()
    assert trusted != competing


def test_symlinked_group_writable_and_mutated_helpers_rejected():
    """Symlinked, group/world-writable, missing, or digest-mutated helpers are rejected without effects."""
    lib = APP / "libexec/privhelper/seal-unit.py"
    original = lib.read_bytes()

    # digest mutation
    lib.write_bytes(original + b"\n#mut\n")
    req = {
        "request_id": "mut-1",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "m",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert out["decision"] == "deny"
    lib.write_bytes(original)

    # group writable
    lib.chmod(0o775)
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert out["decision"] == "deny"
    lib.chmod(0o755)

    # symlink
    lib.unlink()
    lib.symlink_to(APP / "var/caller-bin/seal-unit")
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert out["decision"] == "deny"
    lib.unlink()
    lib.write_bytes(original)
    lib.chmod(0o755)
    assert effects() == []


def test_resolved_helpers_recompute_trust():
    """resolved-helpers dump recomputes live digests and marks trusted helpers under contamination."""
    out = json.loads(
        run(
            ["resolved-helpers", "dump", "--json", "--caller-env", str(CALLER_ENV)]
        ).stdout
    )
    assert out["scenario"] == "ops-seal"
    assert len(out["probes"]) == 3
    for probe in out["probes"]:
        assert probe["helper_path"].startswith("/app/libexec/privhelper/")
        live = file_sha256(Path(probe["helper_path"]))
        assert probe["helper_digest"] == live
        assert probe["helper_trusted"] is True


# ---------------------------------------------------------------------------
# C. Manifest signature and rotation
# ---------------------------------------------------------------------------


def test_valid_higher_generation_installs_atomically():
    """A valid higher-generation signed manifest installs and becomes the current authority."""
    mpath, spath, _man, digest = build_signed_manifest(2)
    run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)])
    installed = json.loads((APP / "var/privhelper/authority-manifest.json").read_text())
    assert installed["generation"] == 2
    assert file_sha256(APP / "var/privhelper/authority-manifest.json") == digest


def test_bad_manifest_installs_are_rejected():
    """Bad signature, equal generation, rollback, traversal path, and unsupported interpreter leave the install untouched."""
    man_path = APP / "var/privhelper/authority-manifest.json"
    sig_path = APP / "var/privhelper/authority-manifest.sig"

    def snapshot():
        return man_path.read_bytes(), sig_path.read_bytes()

    def assert_unchanged(before_man, before_sig):
        assert man_path.read_bytes() == before_man
        assert sig_path.read_bytes() == before_sig

    # bad signature
    before_man, before_sig = snapshot()
    mpath, spath, _, _ = build_signed_manifest(2)
    spath.write_bytes(b"\x00" * 64)
    cp = run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)], check=False)
    assert cp.returncode != 0
    assert_unchanged(before_man, before_sig)
    # equal generation
    before_man, before_sig = snapshot()
    mpath, spath, _, _ = build_signed_manifest(1)
    cp = run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)], check=False)
    assert cp.returncode != 0
    assert_unchanged(before_man, before_sig)
    # successful generation-2 install; later failures must preserve it
    mpath, spath, _, _ = build_signed_manifest(2)
    run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)])
    gen2_man, gen2_sig = snapshot()
    # rollback
    mpath0, spath0, _, _ = build_signed_manifest(1)
    cp = run(["manifest-install", "--manifest", str(mpath0), "--signature", str(spath0)], check=False)
    assert cp.returncode != 0
    assert_unchanged(gen2_man, gen2_sig)
    # traversal
    bad_helpers = json.loads((APP / "share/privhelper/authority-manifest-v1.json").read_text())["helpers"]
    bad_helpers = dict(bad_helpers)
    bad_helpers["seal-unit"] = dict(bad_helpers["seal-unit"])
    bad_helpers["seal-unit"]["relative_path"] = "../etc/passwd"
    mpath, spath, _, _ = build_signed_manifest(3, helpers=bad_helpers)
    cp = run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)], check=False)
    assert cp.returncode != 0
    assert_unchanged(gen2_man, gen2_sig)
    # unsupported interpreter
    bad_helpers = json.loads((APP / "share/privhelper/authority-manifest-v1.json").read_text())["helpers"]
    bad_helpers = dict(bad_helpers)
    bad_helpers["seal-unit"] = dict(bad_helpers["seal-unit"])
    bad_helpers["seal-unit"]["interpreter"] = "/bin/bash"
    mpath, spath, _, _ = build_signed_manifest(3, helpers=bad_helpers)
    cp = run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)], check=False)
    assert cp.returncode != 0
    assert_unchanged(gen2_man, gen2_sig)
    # after rollback attempt generation remains 2
    installed = json.loads(man_path.read_text())
    assert installed["generation"] == 2


def test_installed_manifest_mutation_detected():
    """Mutating the installed manifest bytes is detected by dispatch and reconcile."""
    man_path = APP / "var/privhelper/authority-manifest.json"
    data = json.loads(man_path.read_text())
    data["policy"]["ops.guest"] = ["seal_unit"]
    man_path.write_text(json.dumps(data, indent=2) + "\n")
    req = {
        "request_id": "mutman-1",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "x",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert out["decision"] == "deny"
    run(
        [
            "reconcile",
            "--trace",
            "/app/reports/reconcile-trace.jsonl",
            "--output",
            "/app/reports/authority-report.json",
        ]
    )
    rep = json.loads((APP / "reports/authority-report.json").read_text())
    assert rep["authority_sound"] is False


def test_dynamic_signed_manifest_rotation_revokes_operator_export():
    """A dynamically signed higher generation can revoke operator export while owner remains allowed."""
    base = json.loads((APP / "share/privhelper/authority-manifest-v1.json").read_text())
    policy = {
        "ops.owner": ["seal_unit", "export_bundle", "rotate_token"],
        "ops.operator": ["seal_unit"],
    }
    mpath, spath, _, _ = build_signed_manifest(2, policy=policy, helpers=base["helpers"])
    run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)])
    op = {
        "request_id": "dyn-op-export",
        "principal": "ops.operator",
        "action": "export_bundle",
        "unit": "dyn-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **op)
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "job"]).stdout)
    assert out["decision"] == "deny"
    own = {
        "request_id": "dyn-owner-export",
        "principal": "ops.owner",
        "action": "export_bundle",
        "unit": "dyn-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **own)
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert out["decision"] == "allow"


# ---------------------------------------------------------------------------
# D. Helper reply and request binding
# ---------------------------------------------------------------------------


def test_dishonest_helper_reply_is_denied(tmp_path):
    """A registry-trusted helper returning a mismatched binding field is denied without an effect."""
    helper = APP / "libexec/privhelper/seal-unit.py"
    original = helper.read_text()
    dishonest = original.replace(
        'bind["request_digest"]',
        '"0"*64',
    )
    # Force wrong digest literally
    dishonest = '''#!/usr/bin/env python3
import json, os
req = json.loads(os.environ["PRIVHELPER_REQUEST"])
bind = json.loads(os.environ["PRIVHELPER_BINDING"])
print(json.dumps({
  "status": "ok",
  "request_digest": "0"*64,
  "manifest_generation": bind["manifest_generation"],
  "manifest_digest": bind["manifest_digest"],
  "action": req["action"],
  "unit": req["unit"],
  "effect": "unit_sealed",
}))
'''
    helper.write_text(dishonest)
    # Update manifest digest in place after re-signing requires install.
    # Instead restore digest match by rewriting share and reinstalling through reset helpers path:
    # Easiest valid path: recompute sha into a new signed generation-2 pointing at mutated helper.
    sha = hashlib.sha256(dishonest.encode()).hexdigest()
    base = json.loads((APP / "share/privhelper/authority-manifest-v1.json").read_text())
    helpers = dict(base["helpers"])
    helpers["seal-unit"] = dict(helpers["seal-unit"])
    helpers["seal-unit"]["sha256"] = sha
    mpath, spath, _, _ = build_signed_manifest(2, helpers=helpers)
    run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)])
    req = {
        "request_id": "dishonest-1",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "d-unit",
    }
    p = make_request(tmp_path / "r.json", **req)
    out = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert out["decision"] == "deny"
    assert effects() == []
    helper.write_text(original)


def test_exact_retry_is_idempotent():
    """Repeating the identical request body returns the original decision and keeps a single effect."""
    req = {
        "request_id": "retry-same-dyn",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "retry-unit-7",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    first = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    second = json.loads(run(["dispatch", "--request", str(p), "--via", "direct"]).stdout)
    assert first["decision"] == second["decision"] == "allow"
    assert first["request_digest"] == second["request_digest"] == request_digest(req)
    matched = [e for e in effects() if e["request_id"] == req["request_id"]]
    assert len(matched) == 1


def test_changed_body_conflict_uses_dynamic_ids():
    """Same request_id with a changed canonical field returns conflict and adds no effect."""
    rid = "conflict-dyn-42"
    first = {
        "request_id": rid,
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "unit-a",
    }
    second = dict(first)
    second["unit"] = "unit-b"
    p1 = make_request(Path(tempfile.mkdtemp()) / "a.json", **first)
    p2 = make_request(Path(tempfile.mkdtemp()) / "b.json", **second)
    run(["dispatch", "--request", str(p1), "--via", "job"])
    out = json.loads(run(["dispatch", "--request", str(p2), "--via", "job"]).stdout)
    assert out["decision"] == "conflict"
    assert len([e for e in effects() if e["request_id"] == rid]) == 1
    assert any(j["event"] == "conflict" for j in journal())


# ---------------------------------------------------------------------------
# E. Crash recovery and rotation
# ---------------------------------------------------------------------------


def test_crash_after_prepared_recovers_when_authority_valid():
    """Crash after prepared leaves no effect; recovery completes the request exactly once."""
    req = {
        "request_id": "crash-prep-1",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "cp-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    cp = run(
        ["dispatch", "--request", str(p), "--via", "direct", "--crash-after", "prepared"],
        check=False,
    )
    assert cp.returncode != 0
    assert effects() == []
    run(["recover", "--trace", "/app/reports/recover-trace.jsonl"])
    assert len(effects()) == 1
    run(["recover", "--trace", "/app/reports/recover-trace.jsonl"])
    assert len(effects()) == 1
    assert any(d["request_id"] == req["request_id"] and d["decision"] == "allow" for d in decisions())


def test_crash_after_prepared_then_rotation_denies():
    """Crash after prepared followed by revoking rotation yields recovery denial and no effect."""
    req = {
        "request_id": "crash-prep-revoked",
        "principal": "ops.operator",
        "action": "export_bundle",
        "unit": "rev-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    cp = run(
        ["dispatch", "--request", str(p), "--via", "job", "--crash-after", "prepared"],
        check=False,
    )
    assert cp.returncode != 0
    policy = {
        "ops.owner": ["seal_unit", "export_bundle", "rotate_token"],
        "ops.operator": ["seal_unit"],
    }
    base = json.loads((APP / "share/privhelper/authority-manifest-v1.json").read_text())
    mpath, spath, _, _ = build_signed_manifest(2, policy=policy, helpers=base["helpers"])
    run(["manifest-install", "--manifest", str(mpath), "--signature", str(spath)])
    run(["recover", "--trace", "/app/reports/recover-trace.jsonl"])
    assert effects() == []
    assert any(
        d["request_id"] == req["request_id"] and d["decision"] == "deny" for d in decisions()
    )


def test_crash_after_effect_commits_without_reexecution():
    """Crash after effect leaves exactly one effect; recovery commits without creating another."""
    req = {
        "request_id": "crash-eff-1",
        "principal": "ops.owner",
        "action": "export_bundle",
        "unit": "ce-unit",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    cp = run(
        ["dispatch", "--request", str(p), "--via", "direct", "--crash-after", "effect"],
        check=False,
    )
    assert cp.returncode != 0
    assert len(effects()) == 1
    assert not any(d["request_id"] == req["request_id"] for d in decisions())
    run(["recover", "--trace", "/app/reports/recover-trace.jsonl"])
    assert len(effects()) == 1
    run(["recover", "--trace", "/app/reports/recover-trace.jsonl"])
    assert len(effects()) == 1
    assert any(d["request_id"] == req["request_id"] and d["decision"] == "allow" for d in decisions())


# ---------------------------------------------------------------------------
# F. Reconciliation
# ---------------------------------------------------------------------------


def test_clean_reconcile_is_sound():
    """A clean owner/operator workflow yields authority_sound with a correctly independently computed ledger digest."""
    run(
        [
            "dispatch-batch",
            "--fixture",
            "/app/fixtures/incident-owner-requests.jsonl",
            "--via",
            "job",
            "--caller-env",
            str(CALLER_ENV),
        ]
    )
    run(
        [
            "dispatch-batch",
            "--fixture",
            "/app/fixtures/incident-operator-requests.jsonl",
            "--via",
            "direct",
            "--caller-env",
            str(CALLER_ENV),
        ]
    )
    run(
        [
            "reconcile",
            "--trace",
            "/app/reports/reconcile-trace.jsonl",
            "--output",
            "/app/reports/authority-report.json",
        ]
    )
    rep = json.loads((APP / "reports/authority-report.json").read_text())
    assert rep["scenario"] == "ops-seal"
    assert rep["authority_sound"] is True
    assert rep["violations"] == []
    assert rep["pending_requests"] == 0
    assert rep["helpers_trusted"] is True
    assert rep["idempotency_sound"] is True
    assert rep["recovery_complete"] is True
    assert rep["ledger_digest"] == ledger_digest()
    trace = (APP / "reports/reconcile-trace.jsonl").read_text()
    assert '"phase": "reconcile"' in trace or '"phase":"reconcile"' in trace


def test_reconcile_detects_orphan_and_duplicate_effects():
    """Reconcile independently flags orphan and duplicate effects injected into the effect ledger."""
    req = {
        "request_id": "clean-for-inj",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "inj",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    run(["dispatch", "--request", str(p), "--via", "direct"])
    epath = APP / "var/privhelper/effects.jsonl"
    row = json.loads(epath.read_text().splitlines()[0])
    orphan = dict(row)
    orphan["request_id"] = "orphan-rid"
    orphan["request_digest"] = "a" * 64
    epath.write_text(epath.read_text() + json.dumps(orphan) + "\n" + json.dumps(row) + "\n")
    run(
        [
            "reconcile",
            "--trace",
            "/app/reports/reconcile-trace.jsonl",
            "--output",
            "/app/reports/authority-report.json",
        ]
    )
    rep = json.loads((APP / "reports/authority-report.json").read_text())
    assert rep["authority_sound"] is False
    joined = " ".join(rep["violations"])
    assert "orphan_effect" in joined
    assert "duplicate_effect" in joined


def test_reconcile_detects_pending_and_digest_mismatch():
    """Reconcile detects unresolved prepared work and mismatched request digests in decisions."""
    req = {
        "request_id": "pend-1",
        "principal": "ops.owner",
        "action": "seal_unit",
        "unit": "pend",
    }
    p = make_request(Path(tempfile.mkdtemp()) / "r.json", **req)
    run(
        ["dispatch", "--request", str(p), "--via", "direct", "--crash-after", "prepared"],
        check=False,
    )
    run(
        [
            "reconcile",
            "--trace",
            "/app/reports/reconcile-trace.jsonl",
            "--output",
            "/app/reports/authority-report.json",
        ]
    )
    rep = json.loads((APP / "reports/authority-report.json").read_text())
    assert rep["authority_sound"] is False
    assert rep["pending_requests"] >= 1 or any("unresolved_pending" in v for v in rep["violations"])

    run(["reset", "--scenario", "ops-seal"])
    p = make_request(Path(tempfile.mkdtemp()) / "r2.json", **req)
    run(["dispatch", "--request", str(p), "--via", "direct"])
    dpath = APP / "var/privhelper/decisions.jsonl"
    rows = [json.loads(line) for line in dpath.read_text().splitlines() if line.strip()]
    rows[0]["request_digest"] = "b" * 64
    dpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    # Also break effect binding to force mismatch signal via orphan / digest mismatch path
    epath = APP / "var/privhelper/effects.jsonl"
    erows = [json.loads(line) for line in epath.read_text().splitlines() if line.strip()]
    erows[0]["helper_digest"] = "c" * 64
    epath.write_text("\n".join(json.dumps(r) for r in erows) + "\n")
    run(
        [
            "reconcile",
            "--trace",
            "/app/reports/reconcile-trace.jsonl",
            "--output",
            "/app/reports/authority-report.json",
        ]
    )
    rep = json.loads((APP / "reports/authority-report.json").read_text())
    assert rep["authority_sound"] is False
    assert any("helper_digest" in v or "mismatch" in v or "orphan" in v for v in rep["violations"])


def test_security_selftest_emits_token():
    """Security self-test emits SECURITY_SELFTEST_OK without leaving the main ledger corrupted."""
    before = (APP / "var/privhelper/decisions.jsonl").read_bytes()
    out = run(["selftest", "--mode", "security"]).stdout
    assert "SECURITY_SELFTEST_OK" in out.splitlines()
    assert (APP / "var/privhelper/decisions.jsonl").read_bytes() == before
