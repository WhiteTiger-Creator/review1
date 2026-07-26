"""Behavioral verifier for the ground-station kernel lockdown fortify gate."""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

import pytest

COMMAND = Path("/app/kernel-fortify")
CATALOG = Path("/app/config/sysctl-module-catalog.json")
POLICY = Path("/app/control/policy.json")
LEDGER = Path("/app/ground-canon/ground-lockdown-ledger-v1.json")
SUMMARY = Path("/app/output/gate_summary.json")


def _ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _contract() -> dict:
    return _ledger()["catalog_contract"]


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _policy(**overrides: object) -> dict:
    value = {
        "version": 1,
        "default_action": "LOCK_ACT_ERRNO",
        "errno": 1,
        "station_channel": "ground-v2",
        "lockdown_modes": ["LOCKDOWN_CONFIDENTIALITY", "LOCKDOWN_INTEGRITY"],
        "blocked_sysctls": [],
        "allowed_bands": ["uplink", "telemetry", "ranging"],
        "allow_feature_stacking": True,
        "band_allowlist": ["band-alpha", "band-beta"],
        "leak_score_ceiling": 40,
    }
    value.update(overrides)
    return value


def _manifest(**overrides: object) -> dict:
    value = {
        "station_id": "uplink-north",
        "band_id": "uplink",
        "band": "band-alpha",
        "features": [],
        "additional_sysctls": [],
    }
    value.update(overrides)
    return value


def _run_compile(
    tmp_path: Path,
    policy: dict | None = None,
    manifest: dict | None = None,
    *,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    policy_path = _write_json(tmp_path / "policy.json", policy or _policy())
    manifest_path = _write_json(tmp_path / "manifest.json", manifest or _manifest())
    output = tmp_path / "profile.json"
    result = subprocess.run(
        [
            str(COMMAND),
            "compile",
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--policy",
            str(policy_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return result, output


def _run_audit(
    tmp_path: Path,
    profile: Path,
    trace_text: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(trace_text, encoding="utf-8")
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            str(COMMAND),
            "audit",
            "--report",
            str(report),
            "--trace",
            str(trace),
            "--profile",
            str(profile),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, report


def _severity(seq: int, sysctl: str) -> int:
    return math.floor((len(sysctl) * 37 + seq * 11) / 5)


def _fortify_not_fortified(seq: int, sysctl: str) -> int:
    sev = _severity(seq, sysctl)
    return math.floor((sev * 43 + seq * 17) / 4)


def _fortify_leak(seq: int, sysctl: str, leak_score: int) -> int:
    sev = _severity(seq, sysctl)
    return math.floor((sev * 23 + leak_score + seq * 5) / 3)


def _pressure(
    violation_events: int, unique_denied: int, leak_violations: int, events_total: int
) -> int:
    return math.floor(
        (violation_events * 100 + unique_denied * 31 + leak_violations * 13)
        / max(events_total, 1)
    )


def test_authoritative_ledger_overrides_decoy_documents():
    """The lockdown ledger must declare itself authoritative and list every decoy path."""
    ledger = _ledger()
    assert ledger["authoritative"] is True
    assert ledger["contains_precomputed_outputs"] is False
    for decoy in ledger["override_decoy_documents"]:
        assert Path(decoy).exists()


def test_deployed_catalog_matches_revision_nine_security_contract():
    """The live catalog must exactly expose the ledger revision-9 sysctl sets."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    contract = _contract()
    assert list(catalog.keys()) == contract["top_level_key_order"]
    assert catalog == {
        "revision": contract["required_revision"],
        "baseline": contract["baseline"],
        "features": contract["features"],
        "hard_deny": contract["immutable_floor"],
    }
    assert contract["required_revision"] == 9
    assert catalog["hard_deny"] == [
        "kernel.sysrq",
        "kernel.core_uses_pid",
        "net.ipv4.conf.all.accept_source_route",
        "net.ipv4.conf.default.accept_source_route",
    ]
    assert "fs.protected_hardlinks" in catalog["features"]["leak-shield"]
    assert "kernel.perf_event_paranoid" in catalog["features"]["ptrace-lock"]


def test_live_policy_station_channel_matches_promotion_contract():
    """The deployed policy must advertise the required ground-v2 station channel."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["station_channel"] == _ledger()["policy_promotion"]["required_station_channel"]
    assert policy["station_channel"] == "ground-v2"


def test_compile_merges_deduplicates_blocks_and_sorts_sysctls(tmp_path: Path):
    """Compilation must deterministically merge baseline, features, and additions."""
    contract = _contract()
    policy = _policy(blocked_sysctls=["kernel.perf_event_paranoid"])
    manifest = _manifest(
        features=["leak-shield", "ptrace-lock"],
        additional_sysctls=["vm.mmap_min_addr", "kernel.kptr_restrict"],
    )
    result, output = _run_compile(tmp_path, policy, manifest)
    assert result.returncode == 0, result.stderr
    raw = output.read_bytes()
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    profile = json.loads(raw.decode("utf-8"))
    expected = sorted(
        (
            set(contract["baseline"])
            | set(contract["features"]["leak-shield"])
            | set(contract["features"]["ptrace-lock"])
            | {"vm.mmap_min_addr"}
        )
        - {"kernel.perf_event_paranoid"}
    )
    assert list(profile.keys()) == _ledger()["profile.json"]["top_level_key_order_errno"]
    assert profile["lockdownModes"] == ["LOCKDOWN_CONFIDENTIALITY", "LOCKDOWN_INTEGRITY"]
    assert list(profile["sysctls"][0].keys()) == ["names", "action"]
    assert profile["sysctls"][0]["names"] == expected
    assert (tmp_path / "profile.json.station").read_text(encoding="utf-8") == "uplink-north"
    assert (tmp_path / "profile.policy").exists()


def test_kill_action_profile_omits_errno_and_accepts_boundary_manifest(tmp_path: Path):
    """A no-feature kill-action profile must omit errno and keep ledger key order."""
    policy = _policy(default_action="LOCK_ACT_KILL")
    del policy["errno"]
    manifest = _manifest(station_id="abc", additional_sysctls=["z" * 64])
    result, output = _run_compile(tmp_path, policy, manifest)
    assert result.returncode == 0, result.stderr
    profile = json.loads(output.read_text(encoding="utf-8"))
    assert list(profile.keys()) == _ledger()["profile.json"]["top_level_key_order_kill"]
    assert "defaultErrnoRet" not in profile


@pytest.mark.parametrize("errno_value", [1, 255])
def test_errno_action_accepts_inclusive_lock_errno_boundaries(
    tmp_path: Path, errno_value: int
):
    """Errno values at both documented boundaries must survive compilation."""
    result, output = _run_compile(tmp_path, _policy(errno=errno_value))
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["defaultErrnoRet"] == errno_value


@pytest.mark.parametrize("errno_value", [0, 256, 28.5, "28"])
def test_errno_action_rejects_out_of_range_or_noninteger_values(
    tmp_path: Path, errno_value: object
):
    """Out-of-range, fractional, and string errno values are schema failures."""
    result, output = _run_compile(tmp_path, _policy(errno=errno_value))
    assert result.returncode == 65
    assert not output.exists()


def test_unknown_feature_and_extra_document_fields_are_fatal(tmp_path: Path):
    """Unknown capabilities and undeclared JSON keys must not be silently accepted."""
    invalid_manifest = _manifest(features=["gpu-passthrough"])
    invalid_manifest["notes"] = "not part of the contract"
    result, output = _run_compile(tmp_path, manifest=invalid_manifest)
    assert result.returncode == 65
    assert not output.exists()


def test_unknown_band_id_binding_is_schema_fatal(tmp_path: Path):
    """A station band_id outside policy.allowed_bands must exit 65 without writing."""
    result, output = _run_compile(tmp_path, manifest=_manifest(band_id="deep-space"))
    assert result.returncode == 65
    assert not output.exists()


def test_unknown_band_allowlist_binding_is_schema_fatal(tmp_path: Path):
    """A station band outside policy.band_allowlist must exit 65 without writing."""
    result, output = _run_compile(tmp_path, manifest=_manifest(band="band-gamma"))
    assert result.returncode == 65
    assert not output.exists()


def test_feature_stacking_disabled_rejects_multi_feature_manifest(tmp_path: Path):
    """When allow_feature_stacking is false, more than one feature is schema-invalid."""
    result, output = _run_compile(
        tmp_path,
        policy=_policy(allow_feature_stacking=False),
        manifest=_manifest(features=["leak-shield", "ptrace-lock"]),
    )
    assert result.returncode == 65
    assert not output.exists()


def test_feature_exclusion_pair_leak_shield_and_module_seal_is_fatal(tmp_path: Path):
    """Selecting both members of a ledger feature exclusion pair must exit 65."""
    result, output = _run_compile(
        tmp_path,
        manifest=_manifest(features=["leak-shield", "module-seal"]),
    )
    assert result.returncode == 65
    assert not output.exists()


def test_immutable_floor_request_is_denied_without_replacing_output(tmp_path: Path):
    """An explicit high-risk sysctl request must exit 77 and preserve prior output."""
    output = tmp_path / "profile.json"
    output.write_text('{"sentinel":"preserve"}', encoding="utf-8")
    policy_path = _write_json(tmp_path / "policy.json", _policy())
    manifest_path = _write_json(
        tmp_path / "manifest.json", _manifest(additional_sysctls=["kernel.sysrq"])
    )
    result = subprocess.run(
        [
            str(COMMAND),
            "compile",
            "--policy",
            str(policy_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 77
    assert json.loads(output.read_text(encoding="utf-8")) == {"sentinel": "preserve"}


def test_compiler_enforces_floor_when_catalog_content_is_tampered(tmp_path: Path):
    """Immutable-floor filtering must follow the ledger even if the catalog is rewritten."""
    original = CATALOG.read_bytes()
    catalog = json.loads(original)
    catalog["baseline"].extend(["kernel.sysrq", "kernel.core_uses_pid"])
    catalog["baseline"] = sorted(set(catalog["baseline"]))
    catalog["hard_deny"] = [
        name
        for name in catalog["hard_deny"]
        if name not in {"kernel.sysrq", "kernel.core_uses_pid"}
    ]
    try:
        CATALOG.write_text(json.dumps(catalog), encoding="utf-8")
        result, output = _run_compile(tmp_path)
        assert result.returncode == 0, result.stderr
        allowed = set(json.loads(output.read_text(encoding="utf-8"))["sysctls"][0]["names"])
        assert allowed.isdisjoint(set(_contract()["immutable_floor"]))
    finally:
        CATALOG.write_bytes(original)


def test_feature_sourced_floor_sysctls_are_silently_dropped(tmp_path: Path):
    """Floor names injected through a tampered feature set must drop silently, not exit 77."""
    original = CATALOG.read_bytes()
    catalog = json.loads(original)
    catalog["features"]["leak-shield"] = sorted(
        set(catalog["features"]["leak-shield"])
        | {"kernel.sysrq", "kernel.core_uses_pid"}
    )
    try:
        CATALOG.write_text(json.dumps(catalog), encoding="utf-8")
        result, output = _run_compile(
            tmp_path, manifest=_manifest(features=["leak-shield"])
        )
        assert result.returncode == 0, result.stderr
        allowed = set(json.loads(output.read_text(encoding="utf-8"))["sysctls"][0]["names"])
        assert "kernel.sysrq" not in allowed
        assert "kernel.core_uses_pid" not in allowed
        assert "fs.protected_hardlinks" in allowed
    finally:
        CATALOG.write_bytes(original)


def test_empty_and_malformed_compile_documents_exit_data_error(tmp_path: Path):
    """Empty or syntactically malformed control documents must exit 65."""
    policy = tmp_path / "empty-policy.json"
    manifest = tmp_path / "bad-manifest.json"
    output = tmp_path / "profile.json"
    policy.write_text("", encoding="utf-8")
    manifest.write_text("{", encoding="utf-8")
    result = subprocess.run(
        [
            str(COMMAND),
            "compile",
            "--policy",
            str(policy),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 65
    assert not output.exists()


def test_usage_relative_paths_and_missing_inputs_have_distinct_exit_codes(tmp_path: Path):
    """Unknown, relative, and repeated options exit 64; missing inputs exit 66."""
    unknown = subprocess.run(
        [str(COMMAND), "compile", "--unknown", "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    relative = subprocess.run(
        [
            str(COMMAND),
            "compile",
            "--policy",
            "policy.json",
            "--manifest",
            "manifest.json",
            "--output",
            "profile.json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    repeated = subprocess.run(
        [
            str(COMMAND),
            "compile",
            "--policy",
            str(tmp_path / "one.json"),
            "--policy",
            str(tmp_path / "two.json"),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output",
            str(tmp_path / "profile.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    missing = subprocess.run(
        [
            str(COMMAND),
            "compile",
            "--policy",
            str(tmp_path / "absent.json"),
            "--manifest",
            str(tmp_path / "also-absent.json"),
            "--output",
            str(tmp_path / "profile.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unknown.returncode == 64
    assert relative.returncode == 64
    assert repeated.returncode == 64
    assert missing.returncode == 66


def test_empty_trace_produces_passing_zero_count_report(tmp_path: Path):
    """An empty JSON Lines trace is valid and must produce a zero-count pass."""
    compile_result, profile = _run_compile(tmp_path)
    assert compile_result.returncode == 0, compile_result.stderr
    result, report = _run_audit(tmp_path, profile, "")
    assert result.returncode == 0, result.stderr
    payload = report.read_bytes()
    assert not payload.endswith(b"\n")
    body = json.loads(payload.decode("utf-8"))
    assert list(body.keys()) == _ledger()["audit_report"]["top_level_key_order"]
    assert body == _ledger()["audit_report"]["empty_trace"]
    summary_raw = SUMMARY.read_bytes()
    assert summary_raw.endswith(b"\x1c")
    summary = json.loads(summary_raw[:-1].decode("utf-8"))
    assert list(summary.keys()) == _ledger()["gate_summary.json"]["top_level_key_order"]
    assert summary["pressure_index"] == 0
    assert summary["unique_denied"] == 0
    assert summary["fortify_peak"] == 0
    assert summary["leak_violations"] == 0


def test_audit_precedence_sorts_mixed_not_fortified_and_leak_violations(
    tmp_path: Path,
):
    """Audit must apply reason precedence, per-reason fortify math, and four-key sort."""
    compile_result, profile = _run_compile(
        tmp_path,
        policy=_policy(leak_score_ceiling=50),
        manifest=_manifest(features=["leak-shield"]),
    )
    assert compile_result.returncode == 0, compile_result.stderr
    trace = (
        '{"seq":1,"sysctl":"kernel.kptr_restrict","leak_score":0}\n'
        '{"seq":2,"sysctl":"kernel.sysrq","leak_score":900}\n'
        '{"seq":3,"sysctl":"fs.protected_hardlinks","leak_score":80}\n'
        '{"seq":4,"sysctl":"kernel.core_uses_pid","leak_score":0}\n'
        '{"seq":5,"sysctl":"fs.protected_hardlinks","leak_score":120}'
    )
    result, report = _run_audit(tmp_path, profile, trace)
    assert result.returncode == 3
    body = json.loads(report.read_text(encoding="utf-8"))
    expected_rows = [
        {
            "seq": 2,
            "sysctl": "kernel.sysrq",
            "reason": "not_fortified",
            "severity_weight": _severity(2, "kernel.sysrq"),
            "fortify_score": _fortify_not_fortified(2, "kernel.sysrq"),
            "leak_score": 900,
        },
        {
            "seq": 4,
            "sysctl": "kernel.core_uses_pid",
            "reason": "not_fortified",
            "severity_weight": _severity(4, "kernel.core_uses_pid"),
            "fortify_score": _fortify_not_fortified(4, "kernel.core_uses_pid"),
            "leak_score": 0,
        },
        {
            "seq": 3,
            "sysctl": "fs.protected_hardlinks",
            "reason": "leak_exceeded",
            "severity_weight": _severity(3, "fs.protected_hardlinks"),
            "fortify_score": _fortify_leak(3, "fs.protected_hardlinks", 80),
            "leak_score": 80,
        },
        {
            "seq": 5,
            "sysctl": "fs.protected_hardlinks",
            "reason": "leak_exceeded",
            "severity_weight": _severity(5, "fs.protected_hardlinks"),
            "fortify_score": _fortify_leak(5, "fs.protected_hardlinks", 120),
            "leak_score": 120,
        },
    ]
    expected_rows.sort(
        key=lambda row: (
            -row["fortify_score"],
            row["reason"],
            row["sysctl"],
            row["seq"],
        )
    )
    assert body["status"] == "violation"
    assert body["events_total"] == 5
    assert body["allowed_events"] == 1
    assert body["violation_events"] == 4
    assert body["pressure_index"] == _pressure(4, 3, 2, 5)
    assert body["violations"] == expected_rows
    assert list(body["violations"][0].keys()) == _ledger()["audit_report"]["violation_key_order"]
    summary = json.loads(SUMMARY.read_bytes()[:-1].decode("utf-8"))
    assert summary["unique_denied"] == 3
    assert summary["leak_violations"] == 2
    assert summary["fortify_peak"] == max(row["fortify_score"] for row in expected_rows)
    assert summary["pressure_index"] == body["pressure_index"]


def test_allowlisted_sysctl_at_exact_leak_ceiling_is_not_a_violation(
    tmp_path: Path,
):
    """leak_score equal to leak_score_ceiling must pass; only values above the ceiling violate."""
    compile_result, profile = _run_compile(
        tmp_path,
        policy=_policy(leak_score_ceiling=100),
        manifest=_manifest(features=["leak-shield"]),
    )
    assert compile_result.returncode == 0, compile_result.stderr
    trace = (
        '{"seq":1,"sysctl":"kernel.kptr_restrict","leak_score":0}\n'
        '{"seq":2,"sysctl":"fs.protected_hardlinks","leak_score":100}'
    )
    result, report = _run_audit(tmp_path, profile, trace)
    assert result.returncode == 0, result.stderr
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["violation_events"] == 0
    assert body["violations"] == []


@pytest.mark.parametrize(
    "trace_text",
    [
        '{"seq":1,"sysctl":"kernel.kptr_restrict","leak_score":0}\n\n{"seq":2,"sysctl":"kernel.dmesg_restrict","leak_score":0}',
        '{"seq":1,"sysctl":"kernel.kptr_restrict","leak_score":0}\n{"seq":3,"sysctl":"kernel.dmesg_restrict","leak_score":0}',
        '{"seq":1,"sysctl":"kernel.kptr_restrict","leak_score":0,"pid":9}',
        '{"seq":1,"sysctl":"kernel.kptr_restrict"}',
        '{"seq":1,"sysctl":',
    ],
)
def test_malformed_trace_never_replaces_existing_report(
    tmp_path: Path, trace_text: str
):
    """Blank, noncontiguous, extra-field, missing leak, and broken traces are fatal."""
    compile_result, profile = _run_compile(tmp_path)
    assert compile_result.returncode == 0, compile_result.stderr
    report = tmp_path / "report.json"
    report.write_text('{"sentinel":"preserve"}', encoding="utf-8")
    before_summary = SUMMARY.read_bytes() if SUMMARY.exists() else None
    trace = tmp_path / "trace.jsonl"
    trace.write_text(trace_text, encoding="utf-8")
    result = subprocess.run(
        [
            str(COMMAND),
            "audit",
            "--profile",
            str(profile),
            "--trace",
            str(trace),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 65
    assert json.loads(report.read_text(encoding="utf-8")) == {"sentinel": "preserve"}
    if before_summary is not None:
        assert SUMMARY.read_bytes() == before_summary


def test_catalog_feature_mutation_forces_profile_update(tmp_path: Path):
    """Mutating a catalog feature membership must change the compiled allowlist."""
    original = CATALOG.read_bytes()
    try:
        first, profile = _run_compile(
            tmp_path, manifest=_manifest(features=["leak-shield"])
        )
        assert first.returncode == 0, first.stderr
        before = json.loads(profile.read_text(encoding="utf-8"))["sysctls"][0]["names"]

        catalog = json.loads(original)
        catalog["features"]["leak-shield"] = sorted(
            set(catalog["features"]["leak-shield"]) | {"net.core.bpf_jit_harden"}
        )
        CATALOG.write_text(json.dumps(catalog), encoding="utf-8")

        second, profile = _run_compile(
            tmp_path, manifest=_manifest(features=["leak-shield"])
        )
        assert second.returncode == 0, second.stderr
        after = json.loads(profile.read_text(encoding="utf-8"))["sysctls"][0]["names"]
        assert after != before
        assert "net.core.bpf_jit_harden" in after
    finally:
        CATALOG.write_bytes(original)


def test_runtime_succeeds_when_python_commands_are_blocked(tmp_path: Path):
    """Profile compilation must use shell utilities and never invoke Python."""
    fake_bin = tmp_path / "blocked-python"
    fake_bin.mkdir()
    blocker = "#!/bin/sh\nexit 99\n"
    for name in ("python", "python3", "pypy", "pypy3"):
        executable = fake_bin / name
        executable.write_text(blocker, encoding="utf-8")
        executable.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    result, output = _run_compile(tmp_path, env=env)
    assert result.returncode == 0, result.stderr
    assert output.exists()
