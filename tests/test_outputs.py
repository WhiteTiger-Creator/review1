"""Exactly 26 candidate-facing tests for the Cargo config / source-replacement auditor."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
CANDIDATE_BIN = Path(
    os.environ.get(
        "CANDIDATE_BIN",
        str(APP_ROOT / "auditor/target/release/cargo-config-source-replacement-precedence-auditor"),
    )
)
FIXTURE_SRC = APP_ROOT / "fixture-tree" / "config-root"
DATA = APP_ROOT / "data"
TOP_LEVEL_KEYS = [
    "request_rows",
    "discovered_config_rows",
    "include_rows",
    "effective_value_rows",
    "path_resolution_rows",
    "source_rows",
    "replacement_edge_rows",
    "package_source_rows",
    "lock_reconciliation_rows",
    "integrity_rows",
    "build_rows",
    "rejection_rows",
    "summary",
]
SORT_KEYS = {
    "request_rows": ("request_id",),
    "discovered_config_rows": ("request_id", "load_order", "config_path"),
    "include_rows": ("request_id", "load_order", "included_path"),
    "effective_value_rows": ("request_id", "key"),
    "path_resolution_rows": ("request_id", "key"),
    "source_rows": ("request_id", "source_name"),
    "replacement_edge_rows": ("request_id", "from_source", "edge_index", "to_source"),
    "package_source_rows": ("request_id", "package_name", "version"),
    "lock_reconciliation_rows": ("request_id", "package_name", "version"),
    "integrity_rows": ("request_id", "package_name", "version", "integrity_kind", "details"),
    "build_rows": ("request_id",),
    "rejection_rows": ("request_id", "stage", "reason"),
}


def _require_bins():
    assert CANDIDATE_BIN.is_file() and os.access(CANDIDATE_BIN, os.X_OK), f"missing {CANDIDATE_BIN}"


def _copy_fixture(dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(FIXTURE_SRC, dest)
    return dest


def _run_bin(
    binary: Path,
    fixture_root: Path,
    output: Path,
    *,
    requests: Path | None = None,
    env_overrides: Path | None = None,
    cli_overrides: Path | None = None,
    expect_success: bool = True,
    remove_existing_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    if remove_existing_output and output.exists():
        output.unlink()
    cmd = [
        str(binary),
        "--fixture-root",
        str(fixture_root),
        "--requests",
        str(requests or DATA / "audit_requests.ndjson"),
        "--environment-overrides",
        str(env_overrides or DATA / "environment_overrides.json"),
        "--cli-overrides",
        str(cli_overrides or DATA / "cli_overrides.ndjson"),
        "--source-profiles",
        str(DATA / "source_profiles.json"),
        "--solver-config",
        str(DATA / "solver_config.json"),
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if expect_success:
        assert proc.returncode == 0, proc.stderr
        assert output.is_file() and output.stat().st_size > 0
    return proc


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _row(rows, **pred):
    matches = [r for r in rows if all(r.get(k) == v for k, v in pred.items())]
    assert matches, f"no row matching {pred}"
    return matches[0]


def _eff(report, request_id, key):
    return _row(report["effective_value_rows"], request_id=request_id, key=key)


def _registry_packages(lock_path: Path) -> list[dict]:
    """Parse registry packages from Cargo.lock via tomllib."""
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages: list[dict] = []
    for pkg in data.get("package", []):
        source = pkg.get("source", "")
        checksum = pkg.get("checksum")
        if isinstance(source, str) and source.startswith("registry+") and checksum:
            packages.append(
                {
                    "name": pkg["name"],
                    "version": pkg["version"],
                    "source": source,
                    "checksum": checksum,
                }
            )
    packages.sort(key=lambda p: (p["name"], p["version"]))
    return packages


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sorted_by_keys(rows: list[dict], keys: tuple[str, ...]) -> bool:
    keyed = [tuple(r.get(k) for k in keys) for r in rows]
    return keyed == sorted(keyed)


def _write_single_request(
    path: Path,
    *,
    request_id: str,
    invocation_directory: str,
    environment_profile_id: str = "env-none",
    cli_override_profile_id: str = "cli-none",
    run_build: bool = False,
) -> None:
    payload = {
        "request_id": request_id,
        "invocation_directory": invocation_directory,
        "environment_profile_id": environment_profile_id,
        "cli_override_profile_id": cli_override_profile_id,
        "workspace_manifest": "project/workspace/Cargo.toml",
        "existing_lock": "project/workspace/Cargo.lock",
        "run_build": run_build,
        "output_report_name": "audit_report.json",
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


@pytest.fixture(scope="session")
def baseline_report(tmp_path_factory):
    _require_bins()
    base = tmp_path_factory.mktemp("baseline")
    fixture = _copy_fixture(base / "fixture")
    cand_out = base / "cand.json"
    _run_bin(CANDIDATE_BIN, fixture, cand_out)
    return _load(cand_out), fixture


def test_01_root_schemas_and_fatal_stale_output_cleanup(tmp_path):
    """Public schemas exist; fatal invalid fixture-root removes a stale final report."""
    _require_bins()
    for name in [
        "data_contract.md",
        "discovery_contract.md",
        "include_contract.md",
        "merge_contract.md",
        "path_contract.md",
        "source_replacement_contract.md",
        "report_schema.md",
        "report.schema.json",
    ]:
        assert (APP_ROOT / "docs" / name).is_file()
    schema = json.loads((APP_ROOT / "docs" / "report.schema.json").read_text(encoding="utf-8"))
    assert schema.get("$schema", "").endswith("draft-07/schema#")
    assert "config_file" in schema["definitions"]["EffectiveValueRow"]["properties"]["merge_layer"]["enum"]

    out = tmp_path / "audit_report.json"
    tmp = Path(str(out) + ".tmp")
    out.write_bytes(b'{"sentinel":"stale-final-report"}\n')
    tmp.write_bytes(b'{"sentinel":"stale-temporary-sibling"}\n')
    bad = tmp_path / "not-a-dir"
    bad.write_text("x", encoding="utf-8")
    proc = _run_bin(
        CANDIDATE_BIN,
        bad,
        out,
        expect_success=False,
        remove_existing_output=False,
    )
    assert proc.returncode != 0
    assert proc.stderr.strip() != ""
    assert not out.exists()
    assert not tmp.exists()

    # Missing fixture-root path is also whole-run fatal.
    missing = tmp_path / "missing-fixture-root"
    out2 = tmp_path / "audit_report_missing.json"
    out2.write_bytes(b'{"sentinel":"stale"}\n')
    proc2 = _run_bin(
        CANDIDATE_BIN,
        missing,
        out2,
        expect_success=False,
        remove_existing_output=False,
    )
    assert proc2.returncode != 0
    assert proc2.stderr.strip() != ""
    assert not out2.exists()
    assert not Path(str(out2) + ".tmp").exists()


def test_02_hierarchical_configuration_discovery(baseline_report):
    """Discovery walks invocation → fixture root with 1-based shallow-to-deep load_order."""
    cand, fixture = baseline_report
    rows = [r for r in cand["discovered_config_rows"] if r["request_id"] == "req-hierarchy-vendor"]
    assert len(rows) == 3
    ordered = sorted(rows, key=lambda r: r["load_order"])
    assert [r["load_order"] for r in ordered] == [1, 2, 3]
    assert ordered[0]["discovery_depth"] > ordered[-1]["discovery_depth"]
    assert ordered[-1]["discovery_depth"] == 0
    for r in ordered:
        assert not Path(r["config_path"]).is_absolute()
        assert "/" in r["config_path"] or r["config_path"].endswith("config.toml")
        assert (fixture / r["config_path"]).is_file()
        assert r["config_path"].endswith(".cargo/config.toml")
    # Shallowest is closest to fixture root.
    assert ordered[0]["config_path"] == ".cargo/config.toml" or ordered[0]["config_path"].endswith(
        "/.cargo/config.toml"
    )
    assert any("project/workspace" in r["config_path"] for r in ordered)


def test_03_scalar_merge_precedence(baseline_report):
    """Deeper scalars replace shallower ones with public provenance fields."""
    cand, _ = baseline_report
    v = _eff(cand, "req-root-discovery", "build.jobs")
    assert v["canonical_value"] == "4"
    assert v["value_type"] == "integer"
    assert v["merge_layer"] == "config_file"
    assert v["defining_source"].endswith(".cargo/config.toml")
    assert v["environment_override_or_null"] is None
    assert v["cli_override_sequence_or_null"] is None


def test_04_array_merge_ordering(baseline_report):
    """Arrays join with higher-precedence items later using compact JSON encoding."""
    cand, _ = baseline_report
    raw = _eff(cand, "req-root-discovery", "build.rustflags")["canonical_value"]
    assert raw == json.dumps(json.loads(raw), separators=(",", ":"))
    c = json.loads(raw)
    assert c[0:2] == ["-C", "opt-level=2"]
    assert "-C" in c and "debuginfo=0" in c
    assert any("link-arg" in x for x in c)


def test_05_recursive_table_merge_behavior(baseline_report):
    """Source tables merge recursively across hierarchy and includes."""
    cand, _ = baseline_report
    assert (
        _eff(cand, "req-root-discovery", "source.crates-io.replace-with")["canonical_value"]
        == "vendor-bridge"
    )
    assert any(
        r["key"].startswith("source.vendor-primary.")
        for r in cand["effective_value_rows"]
        if r["request_id"] == "req-root-discovery"
    )


def test_06_recursive_include_loading(baseline_report):
    """Recursive include chain is reported with depth order and affects rustflags."""
    cand, _ = baseline_report
    rows = [r for r in cand["include_rows"] if r["request_id"] == "req-hierarchy-vendor"]
    root_base = _row(
        rows,
        including_file=".cargo/config.toml",
        included_path="shared/base.toml",
        optional=False,
        exists=True,
    )
    base_arrays = _row(
        rows,
        including_file="shared/base.toml",
        included_path="shared/arrays.toml",
        optional=False,
        exists=True,
    )
    project_source = _row(
        rows,
        including_file="project/.cargo/config.toml",
        included_path="project/config/source.toml",
        optional=False,
        exists=True,
    )
    for r in (root_base, base_arrays, project_source):
        assert not Path(r["included_path"]).is_absolute()
        assert r["exists"] is True
        assert r["load_order"] >= 1
    assert base_arrays["include_depth"] > root_base["include_depth"]
    assert root_base["load_order"] < base_arrays["load_order"]
    selected = sorted(
        [root_base, base_arrays, project_source],
        key=lambda r: r["load_order"],
    )
    orders = [r["load_order"] for r in selected]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)
    flags = json.loads(_eff(cand, "req-hierarchy-vendor", "build.rustflags")["canonical_value"])
    assert flags[0:2] == ["-C", "opt-level=2"]


def test_07_left_to_right_include_precedence(tmp_path):
    """Later includes override earlier ones; including-file scalars win afterward."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    (fixture / "shared" / "ltr_first.toml").write_text(
        '[build]\njobs = 31\nrustflags = ["first"]\n',
        encoding="utf-8",
    )
    (fixture / "shared" / "ltr_second.toml").write_text(
        '[build]\njobs = 47\nrustflags = ["second"]\n',
        encoding="utf-8",
    )
    (fixture / ".cargo" / "config.toml").write_text(
        'include = [\n'
        '  { path = "../shared/ltr_first.toml" },\n'
        '  { path = "../shared/ltr_second.toml" },\n'
        "]\n\n"
        "[build]\n"
        "jobs = 59\n"
        'rustflags = ["own"]\n\n'
        "[source.crates-io]\n"
        'replace-with = "vendor-bridge"\n\n'
        "[source.vendor-bridge]\n"
        'replace-with = "vendor-primary"\n\n'
        "[source.vendor-primary]\n"
        'directory = "project/workspace/vendor-primary"\n',
        encoding="utf-8",
    )
    # Neutralize deeper hierarchical build keys so the including root wins.
    (fixture / "project" / ".cargo" / "config.toml").write_text(
        'include = [\n'
        '  { path = "../config/source.toml" },\n'
        '  { path = "../config/missing-optional.toml", optional = true },\n'
        "]\n\n"
        "[term]\n"
        "verbose = false\n",
        encoding="utf-8",
    )
    (fixture / "project" / "workspace" / ".cargo" / "config.toml").write_text(
        '[build]\ntarget-dir = "target-audit"\n\n[term]\ncolor = "never"\n',
        encoding="utf-8",
    )
    req = tmp_path / "req.ndjson"
    _write_single_request(
        req,
        request_id="req-ltr-includes",
        invocation_directory="project/workspace",
        environment_profile_id="env-none",
        cli_override_profile_id="cli-none",
        run_build=False,
    )
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out, requests=req)
    rep = _load(out)
    jobs = _eff(rep, "req-ltr-includes", "build.jobs")
    assert jobs["canonical_value"] == "59"
    assert jobs["merge_layer"] == "config_file"
    assert jobs["defining_source"] == ".cargo/config.toml"
    assert jobs["canonical_value"] not in ("31", "47")
    flags_raw = _eff(rep, "req-ltr-includes", "build.rustflags")["canonical_value"]
    assert flags_raw == json.dumps(json.loads(flags_raw), separators=(",", ":"))
    flags = json.loads(flags_raw)
    assert flags == ["first", "second", "own"]
    includes = [r for r in rep["include_rows"] if r["request_id"] == "req-ltr-includes"]
    first = _row(includes, included_path="shared/ltr_first.toml", exists=True, optional=False)
    second = _row(includes, included_path="shared/ltr_second.toml", exists=True, optional=False)
    assert first["load_order"] < second["load_order"]
    assert first["including_file"] == ".cargo/config.toml"
    assert second["including_file"] == ".cargo/config.toml"


def test_08_optional_missing_include(tmp_path):
    """Optional missing include is recorded; recursion continues to later includes."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    (fixture / "shared" / "opt_a.toml").write_text(
        '[build]\njobs = 11\nrustflags = ["from-a"]\n',
        encoding="utf-8",
    )
    (fixture / "shared" / "opt_b.toml").write_text(
        '[build]\njobs = 22\nrustflags = ["from-b"]\n',
        encoding="utf-8",
    )
    (fixture / ".cargo" / "config.toml").write_text(
        'include = [\n'
        '  { path = "../shared/opt_a.toml" },\n'
        '  { path = "../shared/missing-optional-mid.toml", optional = true },\n'
        '  { path = "../shared/opt_b.toml" },\n'
        "]\n\n"
        "[build]\n"
        "jobs = 33\n"
        'rustflags = ["own-root"]\n\n'
        "[source.crates-io]\n"
        'replace-with = "vendor-bridge"\n\n'
        "[source.vendor-bridge]\n"
        'replace-with = "vendor-primary"\n\n'
        "[source.vendor-primary]\n"
        'directory = "project/workspace/vendor-primary"\n',
        encoding="utf-8",
    )
    (fixture / "project" / ".cargo" / "config.toml").write_text(
        'include = [\n'
        '  { path = "../config/source.toml" },\n'
        "]\n\n"
        "[term]\n"
        "verbose = false\n",
        encoding="utf-8",
    )
    (fixture / "project" / "workspace" / ".cargo" / "config.toml").write_text(
        '[build]\ntarget-dir = "target-audit"\n\n[term]\ncolor = "never"\n',
        encoding="utf-8",
    )
    req = tmp_path / "req.ndjson"
    _write_single_request(
        req,
        request_id="req-optional-mid",
        invocation_directory="project/workspace",
        environment_profile_id="env-none",
        cli_override_profile_id="cli-none",
        run_build=False,
    )
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out, requests=req)
    rep = _load(out)
    assert _row(rep["request_rows"], request_id="req-optional-mid")["status"] == "accepted"
    rows = [r for r in rep["include_rows"] if r["request_id"] == "req-optional-mid"]
    a = _row(rows, included_path="shared/opt_a.toml", exists=True, optional=False)
    missing = _row(
        rows,
        included_path="shared/missing-optional-mid.toml",
        exists=False,
        optional=True,
    )
    b = _row(rows, included_path="shared/opt_b.toml", exists=True, optional=False)
    assert a["load_order"] < missing["load_order"] < b["load_order"]
    assert missing["optional"] is True
    assert missing["exists"] is False
    assert missing["including_file"] == ".cargo/config.toml"
    assert a["including_file"] == b["including_file"] == ".cargo/config.toml"
    flags_raw = _eff(rep, "req-optional-mid", "build.rustflags")["canonical_value"]
    assert flags_raw == json.dumps(json.loads(flags_raw), separators=(",", ":"))
    flags = json.loads(flags_raw)
    assert flags == ["from-a", "from-b", "own-root"]
    assert _eff(rep, "req-optional-mid", "build.jobs")["canonical_value"] == "33"
    assert _eff(rep, "req-optional-mid", "build.jobs")["defining_source"] == ".cargo/config.toml"


def test_09_required_missing_include(tmp_path):
    """Required missing include rejects the request with documented stage/reason."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    arrays = fixture / "shared" / "arrays.toml"
    arrays.rename(arrays.with_suffix(".toml.hidden"))
    cfg = fixture / ".cargo" / "config.toml"
    cfg.write_text(
        'include = ["../shared/does-not-exist.toml"]\n\n[build]\njobs = 2\n',
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out)
    rep = _load(out)
    rej = _row(rep["rejection_rows"], reason="required_include_missing")
    assert rej["stage"] == "include"


def test_10_include_cycle_detection(tmp_path):
    """Include cycles are rejected deterministically with documented stage/reason."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    a = fixture / "shared" / "cycle_a.toml"
    b = fixture / "shared" / "cycle_b.toml"
    a.write_text('include = ["cycle_b.toml"]\n[build]\njobs = 1\n', encoding="utf-8")
    b.write_text('include = ["cycle_a.toml"]\n[build]\njobs = 2\n', encoding="utf-8")
    cfg = fixture / ".cargo" / "config.toml"
    cfg.write_text('include = [{ path = "../shared/cycle_a.toml" }]\n', encoding="utf-8")
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out)
    rep = _load(out)
    rej = _row(rep["rejection_rows"], reason="include_cycle")
    assert rej["stage"] == "include"


def test_11_environment_override_precedence(baseline_report):
    """Environment overrides win over configuration files with public provenance."""
    cand, _ = baseline_report
    v = _eff(cand, "req-hierarchy-vendor", "term.verbose")
    assert v["canonical_value"] == "true"
    assert v["merge_layer"] == "environment"
    assert v["defining_source"] == "environment"
    assert v["environment_override_or_null"] == "CARGO_TERM_VERBOSE"
    assert v["cli_override_sequence_or_null"] is None


def test_12_multiple_config_overrides_left_to_right(baseline_report):
    """Multiple --config overrides merge left to right with CLI provenance."""
    cand, _ = baseline_report
    jobs = _eff(cand, "req-hierarchy-vendor", "build.jobs")
    assert jobs["canonical_value"] == "8"
    assert jobs["merge_layer"] == "cli"
    assert jobs["cli_override_sequence_or_null"] == 2
    assert jobs["environment_override_or_null"] is None
    assert jobs["defining_source"].endswith(".toml") or jobs["defining_source"].startswith("cli:")


def test_13_environment_versus_command_line_precedence(baseline_report):
    """CLI beats environment for overlapping keys; environment-only keys remain env."""
    cand, _ = baseline_report
    jobs = _eff(cand, "req-hierarchy-vendor", "build.jobs")
    assert jobs["canonical_value"] == "8"
    assert jobs["merge_layer"] == "cli"
    verbose = _eff(cand, "req-hierarchy-vendor", "term.verbose")
    assert verbose["canonical_value"] == "true"
    assert verbose["merge_layer"] == "environment"
    assert verbose["defining_source"] == "environment"


def test_14_config_relative_path_resolution(baseline_report):
    """Config-file paths resolve relative to the documented config path base."""
    cand, _ = baseline_report
    row = _row(
        cand["path_resolution_rows"],
        request_id="req-root-discovery",
        key="source.vendor-primary.directory",
    )
    # Defined in fixture-root .cargo/config.toml → base is fixture root ("").
    assert row["raw_path"] == "project/workspace/vendor-primary"
    assert row["base_path"] == ""
    assert row["normalized_path"] == "project/workspace/vendor-primary"
    assert row["exists"] is True
    target = _row(
        cand["path_resolution_rows"],
        request_id="req-root-discovery",
        key="build.target-dir",
    )
    assert target["base_path"] == "project/workspace"
    assert target["normalized_path"] == "project/workspace/target-audit"
    assert target["raw_path"] == "target-audit"
    # target-dir need not exist on disk before a build.
    assert target["exists"] is False


def test_15_environment_and_cli_file_relative_path_resolution(tmp_path):
    """CLI file path overrides resolve relative to the defining file base."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    override = fixture / "project" / "config" / "path-override.toml"
    override.write_text(
        '[source.vendor-primary]\ndirectory = "workspace/vendor-primary"\n',
        encoding="utf-8",
    )
    cli = tmp_path / "cli.ndjson"
    cli.write_text(
        json.dumps(
            {
                "profile_id": "cli-path-primary",
                "sequence": 1,
                "override_kind": "file",
                "value": "project/config/path-override.toml",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    req = tmp_path / "req.ndjson"
    _write_single_request(
        req,
        request_id="req-path-cli-primary",
        invocation_directory="project/workspace/crates/cli",
        cli_override_profile_id="cli-path-primary",
        run_build=False,
    )
    out_c = tmp_path / "c.json"
    _run_bin(CANDIDATE_BIN, fixture, out_c, requests=req, cli_overrides=cli)
    rep = _load(out_c)
    eff = _eff(rep, "req-path-cli-primary", "source.vendor-primary.directory")
    assert eff["merge_layer"] == "cli"
    assert eff["defining_source"] == "project/config/path-override.toml"
    row = _row(
        rep["path_resolution_rows"],
        request_id="req-path-cli-primary",
        key="source.vendor-primary.directory",
    )
    assert row["raw_path"] == "workspace/vendor-primary"
    assert row["base_path"] == "project"
    assert row["normalized_path"] == "project/workspace/vendor-primary"
    assert row["exists"] is True
    assert eff["value_type"] == "string"
    assert eff["cli_override_sequence_or_null"] == 1
    assert eff["environment_override_or_null"] is None

    # Control: without the CLI file override, provenance must not be the override file.
    req_ctrl = tmp_path / "req-ctrl.ndjson"
    _write_single_request(
        req_ctrl,
        request_id="req-path-cli-control",
        invocation_directory="project/workspace/crates/cli",
        cli_override_profile_id="cli-none",
        run_build=False,
    )
    out_ctrl = tmp_path / "ctrl.json"
    _run_bin(CANDIDATE_BIN, fixture, out_ctrl, requests=req_ctrl)
    ctrl = _eff(_load(out_ctrl), "req-path-cli-control", "source.vendor-primary.directory")
    assert ctrl["defining_source"] != "project/config/path-override.toml"
    assert ctrl["merge_layer"] == "config_file"

    override.write_text(
        '[source.vendor-primary]\ndirectory = "workspace/./vendor-primary"\n',
        encoding="utf-8",
    )
    out_eq = tmp_path / "eq.json"
    _run_bin(CANDIDATE_BIN, fixture, out_eq, requests=req, cli_overrides=cli)
    row_eq = _row(
        _load(out_eq)["path_resolution_rows"],
        request_id="req-path-cli-primary",
        key="source.vendor-primary.directory",
    )
    assert row_eq["normalized_path"] == row["normalized_path"]


def test_16_direct_source_replacement(baseline_report):
    """crates-io replace-with is present with public source_kind and terminal_source string."""
    cand, _ = baseline_report
    row = _row(cand["source_rows"], request_id="req-root-discovery", source_name="crates-io")
    assert row["source_kind"] == "replace"
    assert row["replace_with_or_null"] == "vendor-bridge"
    assert isinstance(row["terminal_source"], str)
    assert row["terminal_source"] not in (True, False, "true", "false")
    assert row["terminal_source"] == "vendor-primary"
    assert row["root_path_or_null"] is None


def test_17_multi_step_source_replacement_chain(baseline_report):
    """crates-io → vendor-bridge → vendor-primary uses 1-based edges and terminal names."""
    cand, _ = baseline_report
    edges = [
        r
        for r in cand["replacement_edge_rows"]
        if r["request_id"] == "req-hierarchy-vendor"
    ]
    e1 = _row(edges, from_source="crates-io", to_source="vendor-bridge", edge_index=1)
    assert e1["edge_index"] == 1
    # Within the crates-io exploration chain, the second hop is edge_index=2.
    e2 = _row(edges, from_source="vendor-bridge", to_source="vendor-primary", edge_index=2)
    assert e2["edge_index"] == 2
    # Exploring vendor-bridge as its own origin also emits a 1-based first edge.
    bridge_origin = _row(
        edges, from_source="vendor-bridge", to_source="vendor-primary", edge_index=1
    )
    assert bridge_origin["edge_index"] == 1
    crates = _row(cand["source_rows"], request_id="req-hierarchy-vendor", source_name="crates-io")
    assert crates["replace_with_or_null"] == "vendor-bridge"
    assert crates["terminal_source"] == "vendor-primary"
    assert isinstance(crates["terminal_source"], str)
    bridge = _row(cand["source_rows"], request_id="req-hierarchy-vendor", source_name="vendor-bridge")
    assert bridge["replace_with_or_null"] == "vendor-primary"
    assert bridge["terminal_source"] == "vendor-primary"
    primary = _row(
        cand["source_rows"], request_id="req-hierarchy-vendor", source_name="vendor-primary"
    )
    assert primary["source_kind"] == "directory"
    assert primary["terminal_source"] == "vendor-primary"
    assert primary["root_path_or_null"] is not None
    assert "vendor-primary" in primary["root_path_or_null"]


def test_18_replacement_cycle_rejection(tmp_path):
    """Replacement cycles are rejected with documented stage/reason."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    cfg = fixture / ".cargo" / "config.toml"
    cfg.write_text(
        "[source.crates-io]\nreplace-with = \"a\"\n\n"
        "[source.a]\nreplace-with = \"b\"\n\n"
        "[source.b]\nreplace-with = \"a\"\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out)
    rep = _load(out)
    rej = _row(rep["rejection_rows"], reason="replacement_cycle")
    assert rej["stage"] == "source"


def test_19_directory_source_package_identity(baseline_report):
    """Directory terminal source identity for audit-core matches lock + Cargo.toml."""
    cand, fixture = baseline_report
    pkgs = _registry_packages(fixture / "project/workspace/Cargo.lock")
    audit_core = next(p for p in pkgs if p["name"] == "audit-core")
    version = audit_core["version"]
    row = _row(
        cand["package_source_rows"],
        request_id="req-hierarchy-vendor",
        package_name="audit-core",
        version=version,
    )
    assert row["terminal_source"] == "vendor-primary"
    assert row["relative_package_path"] == f"project/workspace/vendor-primary/audit-core-{version}"
    assert row["original_source"] == audit_core["source"]
    ident = _row(
        cand["integrity_rows"],
        request_id="req-hierarchy-vendor",
        package_name="audit-core",
        version=version,
        integrity_kind="directory_identity",
    )
    assert ident["status"] == "ok"
    assert ident["details"] == "manifest matches"
    checksum = _row(
        cand["integrity_rows"],
        request_id="req-hierarchy-vendor",
        package_name="audit-core",
        version=version,
        integrity_kind="directory_checksum",
    )
    assert checksum["status"] == "ok"
    assert checksum["details"]
    manifest = tomllib.loads(
        (fixture / row["relative_package_path"] / "Cargo.toml").read_text(encoding="utf-8")
    )
    assert manifest["package"]["name"] == "audit-core"
    assert manifest["package"]["version"] == version
    assert (fixture / row["relative_package_path"]).is_dir()


def test_20_local_registry_index_and_archive_identity(baseline_report):
    """Local-registry integrity for audit-core matches index + independently hashed archive."""
    cand, fixture = baseline_report
    pkgs = _registry_packages(fixture / "project/workspace/Cargo.lock")
    audit_core = next(p for p in pkgs if p["name"] == "audit-core")
    version = audit_core["version"]
    rid = "req-project-local-registry"
    for kind in (
        "local_registry_index",
        "local_registry_archive",
        "local_registry_identity",
        "local_registry_path",
    ):
        row = _row(
            cand["integrity_rows"],
            request_id=rid,
            package_name="audit-core",
            version=version,
            integrity_kind=kind,
        )
        assert row["status"] == "ok"
    archive = fixture / "project/workspace/local-registry" / f"audit-core-{version}.crate"
    expected_sha = _sha256_file(archive)
    arch_row = _row(
        cand["integrity_rows"],
        request_id=rid,
        package_name="audit-core",
        version=version,
        integrity_kind="local_registry_archive",
    )
    assert arch_row["details"] == expected_sha
    index_path = fixture / "project/workspace/local-registry/index/au/di/audit-core"
    index_entry = json.loads(index_path.read_text(encoding="utf-8").splitlines()[0])
    assert index_entry["cksum"] == expected_sha
    assert index_entry["cksum"] == audit_core["checksum"]
    index_row = _row(
        cand["integrity_rows"],
        request_id=rid,
        package_name="audit-core",
        version=version,
        integrity_kind="local_registry_index",
    )
    assert index_row["details"] == index_entry["cksum"]
    identity = _row(
        cand["integrity_rows"],
        request_id=rid,
        package_name="audit-core",
        version=version,
        integrity_kind="local_registry_identity",
    )
    assert identity["details"] == "manifest matches"
    path_row = _row(
        cand["integrity_rows"],
        request_id=rid,
        package_name="audit-core",
        version=version,
        integrity_kind="local_registry_path",
    )
    assert path_row["details"] == "safe archive paths"


def test_21_cargo_lock_source_reconciliation(baseline_report):
    """Every locked registry package emits exactly one matched reconciliation row."""
    cand, fixture = baseline_report
    pkgs = _registry_packages(fixture / "project/workspace/Cargo.lock")
    matched = [
        r
        for r in cand["lock_reconciliation_rows"]
        if r["request_id"] == "req-hierarchy-vendor"
    ]
    assert len(matched) == len(pkgs)
    seen: set[tuple[str, str]] = set()
    package_sources = [
        r
        for r in cand["package_source_rows"]
        if r["request_id"] == "req-hierarchy-vendor"
    ]
    assert len(package_sources) == len(pkgs)
    for pkg in pkgs:
        row = _row(matched, package_name=pkg["name"], version=pkg["version"])
        key = (row["package_name"], row["version"])
        assert key not in seen
        seen.add(key)
        assert row["status"] == "matched"
        assert row["lock_source"] == pkg["source"]
        assert row["checksum"]
        assert row["checksum"] == pkg["checksum"]
        assert row["effective_source"] == "directory:project/workspace/vendor-primary"
        assert row["effective_source"].startswith("directory:")
        ps = _row(package_sources, package_name=pkg["name"], version=pkg["version"])
        assert ps["terminal_source"] == "vendor-primary"


def test_22_directory_source_checksum_integrity(tmp_path):
    """Mutating one vendored file rejects that package without blanket source failure."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    pkgs = _registry_packages(fixture / "project/workspace/Cargo.lock")
    audit_core = next(p for p in pkgs if p["name"] == "audit-core")
    other = next(p for p in pkgs if p["name"] != "audit-core")
    lib = (
        fixture
        / f"project/workspace/vendor-primary/audit-core-{audit_core['version']}/src/lib.rs"
    )
    lib.write_text(lib.read_text(encoding="utf-8") + "\n// mutated\n", encoding="utf-8")
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out)
    rep = _load(out)
    hierarchy = _row(rep["request_rows"], request_id="req-hierarchy-vendor")
    assert hierarchy["status"] == "rejected"
    mismatch = _row(
        rep["integrity_rows"],
        request_id="req-hierarchy-vendor",
        package_name="audit-core",
        version=audit_core["version"],
        integrity_kind="directory_file",
        status="checksum_mismatch",
    )
    assert mismatch["status"] == "checksum_mismatch"
    untouched_ok = [
        r
        for r in rep["integrity_rows"]
        if r["request_id"] == "req-hierarchy-vendor"
        and r["package_name"] == other["name"]
        and r["version"] == other["version"]
        and r["integrity_kind"].startswith("directory_")
        and r["status"] == "ok"
    ]
    assert untouched_ok


def test_23_local_registry_archive_mutation_locality(tmp_path):
    """Mutating a local-registry archive affects only that terminal source request."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    archive = fixture / "project/workspace/local-registry/audit-core-0.1.0.crate"
    archive.write_bytes(archive.read_bytes() + b"mut")
    out = tmp_path / "out.json"
    _run_bin(CANDIDATE_BIN, fixture, out)
    rep = _load(out)
    assert any(
        r.get("request_id") == "req-project-local-registry"
        and r.get("integrity_kind") == "local_registry_archive"
        and r.get("status") == "checksum_mismatch"
        for r in rep["integrity_rows"]
    ) or any(
        r.get("request_id") == "req-project-local-registry"
        and r.get("reason") == "checksum_mismatch"
        for r in rep["rejection_rows"]
    )
    # Directory-source request remains semantically accepted / matched.
    hierarchy = _row(rep["request_rows"], request_id="req-hierarchy-vendor")
    assert hierarchy["status"] == "accepted"
    assert any(
        r["request_id"] == "req-hierarchy-vendor" and r["status"] == "matched"
        for r in rep["lock_reconciliation_rows"]
    )


def test_24_locked_offline_builds_from_valid_terminal_sources(baseline_report):
    """Exactly two run_build requests succeed with artifact_count counting only cli."""
    cand, _ = baseline_report
    assert len(cand["build_rows"]) == 2
    ids = {b["request_id"] for b in cand["build_rows"]}
    assert ids == {"req-hierarchy-vendor", "req-project-local-registry"}
    for b in cand["build_rows"]:
        assert b["status"] == "success"
        assert b["exit_code"] == 0
        assert b["lock_unchanged"] is True
        assert b["source_bytes_unchanged"] is True
        assert b["artifact_count"] == 1
        req = _row(cand["request_rows"], request_id=b["request_id"])
        assert req["status"] == "accepted"
        assert req["build_status"] == "success"
        assert not any(r["request_id"] == b["request_id"] for r in cand["rejection_rows"])
    skipped = _row(cand["request_rows"], request_id="req-root-discovery")
    assert skipped["build_status"] == "skipped"


def test_25_input_order_and_equivalent_path_invariance(tmp_path):
    """Physical request order and equivalent relative paths do not change semantics."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    lines = (DATA / "audit_requests.ndjson").read_text(encoding="utf-8").splitlines()
    rev = tmp_path / "rev.ndjson"
    rev.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    equiv = tmp_path / "equiv.ndjson"
    rows = [json.loads(x) for x in lines if x.strip()]
    for r in rows:
        if r["request_id"] == "req-root-discovery":
            r["invocation_directory"] = "project/./workspace/crates/cli"
    payload = "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n"
    equiv.write_text(payload, encoding="utf-8")
    out1 = tmp_path / "a.json"
    out2 = tmp_path / "b.json"
    out3 = tmp_path / "c.json"
    _run_bin(CANDIDATE_BIN, fixture, out1)
    _run_bin(CANDIDATE_BIN, fixture, out2, requests=rev)
    _run_bin(CANDIDATE_BIN, fixture, out3, requests=equiv)
    a, b, c = _load(out1), _load(out2), _load(out3)
    for key in [
        "summary",
        "effective_value_rows",
        "source_rows",
        "replacement_edge_rows",
        "lock_reconciliation_rows",
        "build_rows",
    ]:
        assert a[key] == b[key] == c[key]


def test_26_complete_report_determinism_atomic_failure_anti_hardcoding(tmp_path):
    """Deterministic public report shape, summary consistency, mutation locality, fatal cleanup."""
    _require_bins()
    fixture = _copy_fixture(tmp_path / "fixture")
    digests = []
    reports = []
    for i in range(5):
        out = tmp_path / f"run{i}.json"
        _run_bin(CANDIDATE_BIN, fixture, out)
        raw = out.read_bytes()
        digests.append(hashlib.sha256(raw).hexdigest())
        assert raw.endswith(b"\n")
        assert not raw.endswith(b"\n\n")
        rep = json.loads(raw.decode("utf-8"))
        assert list(rep.keys()) == TOP_LEVEL_KEYS
        reports.append(rep)
        for family, keys in SORT_KEYS.items():
            assert _sorted_by_keys(rep[family], keys), f"{family} not sorted by {keys}"
        summary = rep["summary"]
        assert summary["request_count"] == len(rep["request_rows"])
        accepted = sum(1 for r in rep["request_rows"] if r["status"] == "accepted")
        rejected = sum(1 for r in rep["request_rows"] if r["status"] == "rejected")
        assert summary["accepted_request_count"] == accepted
        assert summary["rejected_request_count"] == rejected
        assert summary["discovered_config_count"] == len(rep["discovered_config_rows"])
        assert summary["include_count"] == len(rep["include_rows"])
        successful = sum(1 for b in rep["build_rows"] if b["status"] == "success")
        failed = sum(1 for b in rep["build_rows"] if b["status"] == "failed")
        assert summary["successful_build_count"] == successful
        assert summary["failed_build_count"] == failed
    assert len(set(digests)) == 1
    assert all(r == reports[0] for r in reports[1:])

    baseline_edges = [
        (e["from_source"], e["to_source"], e["edge_index"])
        for e in reports[0]["replacement_edge_rows"]
        if e["request_id"] == "req-hierarchy-vendor"
        and e["from_source"] in ("crates-io", "vendor-bridge")
    ]

    cfg = fixture / "project/workspace/.cargo/config.toml"
    cfg.write_text(
        '[build]\ntarget-dir = "target-audit"\njobs = 99\n\n[term]\ncolor = "never"\n',
        encoding="utf-8",
    )
    out_mut = tmp_path / "mut.json"
    _run_bin(CANDIDATE_BIN, fixture, out_mut)
    mut = _load(out_mut)
    assert _eff(mut, "req-root-discovery", "build.jobs")["canonical_value"] == "99"
    # Hierarchy request still has CLI precedence for build.jobs (mutation locality).
    assert _eff(mut, "req-hierarchy-vendor", "build.jobs")["canonical_value"] == "8"
    assert _eff(mut, "req-hierarchy-vendor", "build.jobs")["merge_layer"] == "cli"
    mut_edges = [
        (e["from_source"], e["to_source"], e["edge_index"])
        for e in mut["replacement_edge_rows"]
        if e["request_id"] == "req-hierarchy-vendor"
        and e["from_source"] in ("crates-io", "vendor-bridge")
    ]
    assert mut_edges == baseline_edges
    assert mut["summary"]["request_count"] == len(mut["request_rows"])
    assert mut["summary"]["successful_build_count"] == sum(
        1 for b in mut["build_rows"] if b["status"] == "success"
    )

    stale = tmp_path / "fatal.json"
    stale_tmp = Path(str(stale) + ".tmp")
    stale.write_bytes(b'{"sentinel":"stale"}\n')
    stale_tmp.write_bytes(b'{"sentinel":"stale-tmp"}\n')
    bad = tmp_path / "not-a-dir"
    bad.write_text("x", encoding="utf-8")
    proc = _run_bin(
        CANDIDATE_BIN,
        bad,
        stale,
        expect_success=False,
        remove_existing_output=False,
    )
    assert proc.returncode != 0
    assert proc.stderr.strip() != ""
    assert not stale.exists()
    assert not stale_tmp.exists()
