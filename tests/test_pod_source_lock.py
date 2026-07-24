import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path("/opt/pod-lock-desk")
CASE = ROOT / "case"
OUT = ROOT / "out"
BIN = ROOT / "pod-source-lock"
AUTHORITY = ROOT / "POD_LOCK_AUTHORITY.txt"


def read_tsv(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:] if line]


def write_tsv(path, header, rows):
    path.write_text("\n".join(["\t".join(header), *("\t".join(row) for row in rows)]) + "\n", encoding="utf-8")


def run_lock(env=None):
    result = subprocess.run([str(BIN)], check=False, text=True, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    return (OUT / "Podfile.lock").read_text(encoding="utf-8")


def rows(name):
    return read_tsv(OUT / name)


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_case_and_authority():
    files = [AUTHORITY]
    files.extend(sorted(path for path in CASE.rglob("*") if path.is_file()))
    return {str(path.relative_to(ROOT)): file_digest(path) for path in files}


def rewrite_policy(**updates):
    path = CASE / "policy.tsv"
    existing = read_tsv(path)
    for row in existing:
        if row["key"] in updates:
            row["value"] = str(updates[row["key"]]).lower()
    write_tsv(path, ["key", "value"], [[row["key"], row["value"]] for row in existing])


def append_target(row):
    with (CASE / "targets.tsv").open("a", encoding="utf-8") as handle:
        handle.write("\t".join(row) + "\n")


def append_spec(row):
    with (CASE / "specs.tsv").open("a", encoding="utf-8") as handle:
        handle.write("\t".join(row) + "\n")


def replace_case(policy_rows, target_rows, spec_rows, rule_rows):
    if CASE.exists():
        shutil.rmtree(CASE)
    CASE.mkdir()
    write_tsv(CASE / "policy.tsv", ["key", "value"], policy_rows)
    write_tsv(
        CASE / "targets.tsv",
        [
            "target",
            "inherit",
            "platform",
            "platform_version",
            "pod",
            "requirement",
            "subspecs",
            "configurations",
            "linkage",
            "source_pin",
            "checksum_required",
        ],
        target_rows,
    )
    write_tsv(
        CASE / "specs.tsv",
        [
            "source",
            "root",
            "version",
            "subspec",
            "default",
            "platforms",
            "dependencies",
            "checksum",
            "trust",
            "size",
            "status",
            "license",
            "vendored",
            "swift",
            "checksum_present",
        ],
        spec_rows,
    )
    write_tsv(CASE / "rules.tsv", ["kind", "root", "subspec", "value", "detail"], rule_rows)


@pytest.fixture(autouse=True)
def restore_case(tmp_path):
    backup = tmp_path / "case"
    shutil.copytree(CASE, backup)
    yield
    if CASE.exists():
        shutil.rmtree(CASE)
    shutil.copytree(backup, CASE)
    if OUT.exists():
        shutil.rmtree(OUT)


def test_artifact_set_headers_sorting_seal_and_input_immutability():
    """Verify artifact set, stale cleanup, TSV schemas, sorted rows, seal, and immutable inputs."""
    before = snapshot_case_and_authority()
    lock = run_lock()

    assert {path.name for path in OUT.iterdir()} == {
        "Podfile.lock",
        "pods-plan.tsv",
        "seal.txt",
        "source-audit.tsv",
        "subspec-graph.tsv",
    }
    assert "stale.lock" not in {path.name for path in OUT.iterdir()}
    assert lock.endswith("\n")
    assert "STATUS: ok\nUNSATISFIED: -\n" in lock

    expected_headers = {
        "pods-plan.tsv": "root\tsource\tversion\tsubspecs\tsize\ttargets\tconfigurations\tlinkage\tchecksums",
        "subspec-graph.tsv": "from\tto\trequirement\treason",
        "source-audit.tsv": "kind\troot\tsource\tversion\tsubspec\tstatus\treason\tdetail",
    }
    for name, header in expected_headers.items():
        lines = (OUT / name).read_text(encoding="utf-8").splitlines()
        assert lines[0] == header
        assert lines[1:] == sorted(lines[1:])

    digest_input = b"".join(
        (OUT / name).read_bytes()
        for name in ["Podfile.lock", "pods-plan.tsv", "subspec-graph.tsv", "source-audit.tsv"]
    )
    assert (OUT / "seal.txt").read_text(encoding="utf-8") == hashlib.sha256(digest_input).hexdigest() + "\n"
    assert snapshot_case_and_authority() == before


def test_forbidden_external_tools_are_not_used(tmp_path, monkeypatch):
    """Verify resolver behavior does not invoke pod, xcodebuild, ruby, git, curl, or wget."""
    trap = tmp_path / "trap-bin"
    trap.mkdir()
    for name in ["pod", "xcodebuild", "ruby", "git", "curl", "wget"]:
        script = trap / name
        script.write_text("#!/bin/sh\necho forbidden-tool >&2\nexit 99\n", encoding="utf-8")
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{trap}:/usr/bin:/bin")

    lock = run_lock()

    assert "STATUS: ok" in lock


def test_public_plan_selects_expected_sources_versions_subspecs_and_checksums():
    """Verify public selected roots, source choices, default subspec closure, and checksum lists."""
    run_lock()
    plan = {row["root"]: row for row in rows("pods-plan.tsv")}

    assert plan == {
        "CryptoBox": {
            "root": "CryptoBox",
            "source": "corp",
            "version": "1.5.1",
            "subspecs": "Core,TLS",
            "size": "390",
            "targets": "App,AppTests,Widget",
            "configurations": "Debug,Release",
            "linkage": "framework,static",
            "checksums": "cb-core-151,cb-tls-151",
        },
        "ImageFlow": {
            "root": "ImageFlow",
            "source": "corp",
            "version": "1.6.0",
            "subspecs": "Core,Filters",
            "size": "580",
            "targets": "App",
            "configurations": "Release",
            "linkage": "static",
            "checksums": "if-core-160,if-filters-160",
        },
        "MetricsKit": {
            "root": "MetricsKit",
            "source": "cdn",
            "version": "3.0.0",
            "subspecs": "Crash",
            "size": "240",
            "targets": "App,AppTests",
            "configurations": "Debug",
            "linkage": "framework,static",
            "checksums": "mk-crash-300",
        },
        "NetStack": {
            "root": "NetStack",
            "source": "cdn",
            "version": "2.1.4",
            "subspecs": "Core,Reachability,TLS",
            "size": "600",
            "targets": "App,AppTests,Widget",
            "configurations": "Debug,Release",
            "linkage": "framework,static",
            "checksums": "ns-core-214,ns-reach-214,ns-tls-214",
        },
        "TestHarness": {
            "root": "TestHarness",
            "source": "trunk",
            "version": "1.3.0",
            "subspecs": "XCTest",
            "size": "200",
            "targets": "AppTests",
            "configurations": "Debug",
            "linkage": "framework",
            "checksums": "th-xctest-130",
        },
        "WidgetBridge": {
            "root": "WidgetBridge",
            "source": "corp",
            "version": "1.0.1",
            "subspecs": "Core",
            "size": "210",
            "targets": "Widget",
            "configurations": "Release",
            "linkage": "framework",
            "checksums": "wb-core-101",
        },
    }


def test_lockfile_sections_and_dependency_graph_capture_transitive_subspecs():
    """Verify lockfile sections and graph edges for target and dependency subspec requests."""
    lock = run_lock()
    graph = rows("subspec-graph.tsv")

    assert lock.splitlines()[:5] == [
        "PODS:",
        "  - CryptoBox/Core (1.5.1)",
        "  - CryptoBox/TLS (1.5.1)",
        "    - CryptoBox/Core (1.5.1)",
        "  - ImageFlow/Core (1.6.0)",
    ]
    assert "SPEC REPOS:\n  corp:\n    - CryptoBox\n    - ImageFlow\n    - WidgetBridge\n  cdn:" in lock
    assert {
        "from": "pod:ImageFlow/Filters@1.6.0",
        "to": "pod:NetStack/TLS@2.1.4",
        "requirement": "~> 2.1",
        "reason": "dependency",
    } in graph
    assert {
        "from": "target:App",
        "to": "pod:ImageFlow/Core,Filters@1.6.0",
        "requirement": ">=1.4 <2.0",
        "reason": "target",
    } in graph


def test_audit_rows_explain_overrides_and_rejection_gates():
    """Verify source-audit rows expose exact override and gate reasons."""
    run_lock()
    audit = rows("source-audit.tsv")

    assert {
        "kind": "override",
        "root": "MetricsKit",
        "source": "-",
        "version": "3.0.0",
        "subspec": "*",
        "status": "selected",
        "reason": "override",
        "detail": "from=~> 3.1;to=3.0.0",
    } in audit
    for expected in [
        ("CryptoBox", "cdn", "1.6.0", "Core", "license", "GPL-3.0"),
        ("ImageFlow", "trunk", "1.7.0", "-", "source_pin", "corp"),
        ("NetStack", "trunk", "2.1.5", "-", "source_block", "trunk"),
        ("WidgetBridge", "corp", "1.1.0", "Core", "platform", "ios>=15.0"),
        ("NetStack", "cdn", "2.2.0", "Core,Reachability", "status", "prerelease"),
    ]:
        root, source, version, subspec, reason, detail = expected
        assert any(
            row["kind"] == "rejected"
            and row["root"] == root
            and row["source"] == source
            and row["version"] == version
            and row["subspec"] == subspec
            and row["reason"] == reason
            and row["detail"] == detail
            for row in audit
        )
    selected_rows = [row for row in audit if row["kind"] == "selected"]
    assert len(selected_rows) == len({tuple(row.items()) for row in selected_rows})
    assert {
        "kind": "selected",
        "root": "NetStack",
        "source": "cdn",
        "version": "2.1.4",
        "subspec": "TLS",
        "status": "selected",
        "reason": "selected",
        "detail": "App",
    } in audit


def test_whole_plan_limits_make_partial_lock_unsatisfied():
    """Verify max_binary_size and max_warnings produce no_valid_complete_plan after resolution."""
    rewrite_policy(max_binary_size="1000", max_warnings="2")

    lock = run_lock()
    audit = rows("source-audit.tsv")

    assert "STATUS: unsatisfied" in lock
    assert "UNSATISFIED: no_valid_complete_plan" in lock
    assert {
        "kind": "limit",
        "root": "-",
        "source": "-",
        "version": "-",
        "subspec": "-",
        "status": "unsatisfied",
        "reason": "max_binary_size",
        "detail": "2220/1000",
    } in audit
    assert any(row["kind"] == "limit" and row["reason"] == "max_warnings" for row in audit)


def test_source_order_breaks_same_version_size_ties():
    """Verify source_order decides otherwise tied source candidates."""
    append_target(["TieApp", "none", "ios", "14.0", "TiePod", "1.0.0", "-", "Release", "static", "-", "true"])
    for source in ["cdn", "corp"]:
        append_spec([
            source,
            "TiePod",
            "1.0.0",
            "Core",
            "true",
            "ios>=12.0",
            "-",
            f"tie-{source}",
            "90",
            "50",
            "release",
            "MIT",
            "false",
            "true",
            "true",
        ])
    rewrite_policy(max_binary_size="4000")

    run_lock()
    plan = {row["root"]: row for row in rows("pods-plan.tsv")}

    assert plan["TiePod"]["source"] == "corp"
    assert plan["TiePod"]["checksums"] == "tie-corp"


def test_checksum_requirement_controls_missing_checksum_candidates():
    """Verify checksum_required rejects or allows missing checksum rows."""
    append_target(["LooseApp", "none", "ios", "14.0", "LoosePod", ">=1.0 <2.0", "-", "Debug", "framework", "-", "false"])
    append_spec([
        "corp",
        "LoosePod",
        "1.1.0",
        "Core",
        "true",
        "ios>=12.0",
        "-",
        "loose-110",
        "90",
        "55",
        "release",
        "MIT",
        "false",
        "true",
        "false",
    ])
    rewrite_policy(max_binary_size="4000")

    run_lock()
    assert {row["root"]: row for row in rows("pods-plan.tsv")}["LoosePod"]["version"] == "1.1.0"

    append_target(["StrictApp", "none", "ios", "14.0", "StrictPod", ">=1.0 <2.0", "-", "Debug", "framework", "-", "true"])
    append_spec([
        "corp",
        "StrictPod",
        "1.1.0",
        "Core",
        "true",
        "ios>=12.0",
        "-",
        "strict-110",
        "90",
        "55",
        "release",
        "MIT",
        "false",
        "true",
        "false",
    ])

    lock = run_lock()
    assert "no_eligible:StrictPod" in lock
    assert {
        "kind": "rejected",
        "root": "StrictPod",
        "source": "corp",
        "version": "1.1.0",
        "subspec": "Core",
        "status": "rejected",
        "reason": "checksum",
        "detail": "Core",
    } in rows("source-audit.tsv")


def test_tilde_patch_requirement_uses_next_minor_upper_bound():
    """Verify ~> X.Y.Z allows patch upgrades but rejects the next minor."""
    append_target(["PatchApp", "none", "ios", "14.0", "PatchPod", "~> 1.2.3", "-", "Release", "static", "-", "true"])
    append_spec(["corp", "PatchPod", "1.2.3", "Core", "true", "ios>=12.0", "-", "patch-123", "90", "40", "release", "MIT", "false", "true", "true"])
    append_spec(["corp", "PatchPod", "1.2.9", "Core", "true", "ios>=12.0", "-", "patch-129", "90", "40", "release", "MIT", "false", "true", "true"])
    append_spec(["corp", "PatchPod", "1.3.0", "Core", "true", "ios>=12.0", "-", "patch-130", "90", "40", "release", "MIT", "false", "true", "true"])
    rewrite_policy(max_binary_size="4000")

    run_lock()
    plan = {row["root"]: row for row in rows("pods-plan.tsv")}
    audit = rows("source-audit.tsv")

    assert plan["PatchPod"]["version"] == "1.2.9"
    assert any(row["root"] == "PatchPod" and row["version"] == "1.3.0" and row["reason"] == "range" for row in audit)


def test_remaining_requirement_forms_platform_default_and_extra_gates():
    """Verify exact, star, ~> X.Y, >=V, platform defaulting, trust, deprecated, and source gates."""
    append_target(["ExactApp", "none", "-", "-", "ExactPod", "1.0.0", "-", "Release", "static", "-", "true"])
    append_target(["StarApp", "none", "ios", "14.0", "StarPod", "*", "-", "Release", "static", "-", "true"])
    append_target(["MinorApp", "none", "ios", "14.0", "MinorPod", "~> 1.2", "-", "Release", "static", "-", "true"])
    append_target(["AtLeastApp", "none", "ios", "14.0", "AtLeastPod", ">=2.0", "-", "Release", "static", "-", "true"])
    append_target(["BadTrust", "none", "ios", "14.0", "TrustPod", "*", "-", "Release", "static", "-", "true"])
    append_target(["BadStatus", "none", "ios", "14.0", "OldPod", "*", "-", "Release", "static", "-", "true"])
    append_target(["BadSource", "none", "ios", "14.0", "GhostPod", "*", "-", "Release", "static", "-", "true"])
    for row in [
        ["corp", "ExactPod", "1.0.0", "Core", "true", "ios>=13.0", "-", "exact-100", "90", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "ExactPod", "1.0.1", "Core", "true", "ios>=13.0", "-", "exact-101", "90", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "StarPod", "9.0.0", "Core", "true", "ios>=13.0", "-", "star-900", "90", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "MinorPod", "1.2.9", "Core", "true", "ios>=13.0", "-", "minor-129", "90", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "MinorPod", "2.0.0", "Core", "true", "ios>=13.0", "-", "minor-200", "90", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "AtLeastPod", "2.5.0", "Core", "true", "ios>=13.0", "-", "atleast-250", "90", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "TrustPod", "1.0.0", "Core", "true", "ios>=13.0", "-", "trust-100", "20", "10", "release", "MIT", "false", "true", "true"],
        ["corp", "OldPod", "1.0.0", "Core", "true", "ios>=13.0", "-", "old-100", "90", "10", "deprecated", "MIT", "false", "true", "true"],
        ["ghost", "GhostPod", "1.0.0", "Core", "true", "ios>=13.0", "-", "ghost-100", "90", "10", "release", "MIT", "false", "true", "true"],
    ]:
        append_spec(row)
    rewrite_policy(max_binary_size="5000", max_warnings="50")

    lock = run_lock()
    plan = {row["root"]: row for row in rows("pods-plan.tsv")}
    audit = rows("source-audit.tsv")

    assert plan["ExactPod"]["version"] == "1.0.0"
    assert plan["StarPod"]["version"] == "9.0.0"
    assert plan["MinorPod"]["version"] == "1.2.9"
    assert plan["AtLeastPod"]["version"] == "2.5.0"
    assert "no_eligible:GhostPod" in lock
    assert "no_eligible:OldPod" in lock
    assert "no_eligible:TrustPod" in lock
    assert any(row["root"] == "ExactPod" and row["version"] == "1.0.1" and row["reason"] == "range" for row in audit)
    assert any(row["root"] == "MinorPod" and row["version"] == "2.0.0" and row["reason"] == "range" for row in audit)
    assert any(row["root"] == "TrustPod" and row["reason"] == "trust" and row["detail"] == "20" for row in audit)
    assert any(row["root"] == "OldPod" and row["reason"] == "status" and row["detail"] == "deprecated" for row in audit)
    assert any(row["root"] == "GhostPod" and row["reason"] == "source" and row["detail"] == "ghost" for row in audit)


def test_subspec_scoped_source_block_does_not_block_unrequested_subspecs():
    """Verify source_block with a concrete subspec does not reject other subspecs on the same root."""
    replace_case(
        [
            ["case_id", "source-block-scope"],
            ["platform", "ios"],
            ["platform_version", "14.0"],
            ["source_order", "trunk"],
            ["min_trust", "50"],
            ["allow_prerelease", "false"],
            ["max_binary_size", "500"],
            ["max_warnings", "5"],
            ["cocoapods_version", "1.16.1"],
        ],
        [["Demo", "none", "ios", "14.0", "ScopedPod", "1.0.0", "Core", "Release", "static", "-", "true"]],
        [
            ["trunk", "ScopedPod", "1.0.0", "Core", "true", "ios>=12.0", "-", "scoped-core", "80", "40", "release", "MIT", "false", "true", "true"],
            ["trunk", "ScopedPod", "1.0.0", "Extra", "false", "ios>=12.0", "-", "scoped-extra", "80", "40", "release", "MIT", "false", "true", "true"],
        ],
        [
            ["license_allow", "*", "*", "MIT", "-"],
            ["source_block", "ScopedPod", "Extra", "trunk", "block-extra-only"],
        ],
    )

    lock = run_lock()
    plan = {row["root"]: row for row in rows("pods-plan.tsv")}

    assert "STATUS: ok" in lock
    assert plan["ScopedPod"]["subspecs"] == "Core"


def test_graph_is_rebuilt_for_final_selected_tuple_after_later_upgrade():
    """Verify stale edges to an older tuple are replaced by edges to the final selected tuple."""
    replace_case(
        [
            ["case_id", "upgrade-graph"],
            ["platform", "ios"],
            ["platform_version", "14.0"],
            ["source_order", "mirror,trunk"],
            ["min_trust", "50"],
            ["allow_prerelease", "false"],
            ["max_binary_size", "500"],
            ["max_warnings", "5"],
            ["cocoapods_version", "1.16.1"],
        ],
        [
            ["Pinned", "none", "ios", "14.0", "UpgradePod", ">=1.0 <2.0", "Core", "Release", "static", "mirror", "true"],
            ["Open", "none", "ios", "14.0", "UpgradePod", ">=1.0 <2.0", "Core", "Debug", "framework", "-", "true"],
        ],
        [
            ["mirror", "UpgradePod", "1.0.0", "Core", "true", "ios>=12.0", "-", "upgrade-100", "80", "40", "release", "MIT", "false", "true", "true"],
            ["trunk", "UpgradePod", "1.1.0", "Core", "true", "ios>=12.0", "-", "upgrade-110", "80", "40", "release", "MIT", "false", "true", "true"],
        ],
        [["license_allow", "*", "*", "MIT", "-"]],
    )

    run_lock()
    graph_text = (OUT / "subspec-graph.tsv").read_text(encoding="utf-8")

    assert "pod:UpgradePod/Core@1.1.0" in graph_text
    assert "pod:UpgradePod/Core@1.0.0" not in graph_text


def test_no_eligible_slug_is_written_for_missing_subspec_request():
    """Verify no_eligible:<root> is emitted for unsatisfied requested subspecs."""
    append_target(["BadApp", "none", "ios", "14.0", "ImageFlow", ">=1.4 <2.0", "MapKit", "Release", "static", "corp", "true"])

    lock = run_lock()

    assert "STATUS: unsatisfied" in lock
    assert "no_eligible:ImageFlow" in lock
    assert any(row["root"] == "ImageFlow" and row["reason"] == "missing_subspec" for row in rows("source-audit.tsv"))


def test_whole_case_directory_can_be_replaced_with_compatible_schema():
    """Verify the command works when the entire case directory is replaced."""
    replace_case(
        [
            ["case_id", "replacement-pod-case"],
            ["platform", "ios"],
            ["platform_version", "13.0"],
            ["source_order", "mirror,trunk"],
            ["min_trust", "50"],
            ["allow_prerelease", "false"],
            ["max_binary_size", "500"],
            ["max_warnings", "5"],
            ["cocoapods_version", "1.16.1"],
        ],
        [["Demo", "none", "ios", "13.0", "MiniPod", "~> 1.0", "-", "Release", "static", "-", "true"]],
        [
            ["mirror", "MiniPod", "1.0.2", "Core", "true", "ios>=12.0", "HelperPod/Core|*|-|true", "mini-core", "80", "60", "release", "MIT", "false", "true", "true"],
            ["mirror", "HelperPod", "2.0.0", "Core", "true", "ios>=12.0", "-", "helper-core", "80", "70", "release", "MIT", "false", "true", "true"],
        ],
        [["license_allow", "*", "*", "MIT", "-"]],
    )

    lock = run_lock()
    plan = {row["root"]: row for row in rows("pods-plan.tsv")}

    assert "STATUS: ok" in lock
    assert set(plan) == {"HelperPod", "MiniPod"}
    assert plan["MiniPod"]["source"] == "mirror"
    assert {
        "from": "pod:MiniPod/Core@1.0.2",
        "to": "pod:HelperPod/Core@2.0.0",
        "requirement": "*",
        "reason": "dependency",
    } in rows("subspec-graph.tsv")
