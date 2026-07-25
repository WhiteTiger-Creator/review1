"""Candidate-facing verifier for the cmake-reconciler native Rust binary.

Exactly 23 tests (``test_01_*`` .. ``test_26_*``, with gaps). Every test
invokes the candidate through the isolation wrapper when available. Focused
projection checks cover precedence, locks, mutations, and fatal cleanup;
test 26 checks declaration-order invariance, public report-byte contract, and
whole-run fatal cleanup.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
from helpers.io_util import (
    CANDIDATE_BIN,
    assert_fatal,
    binary_ready,
    copy_data_dir,
    read_json,
    read_ndjson,
    restrict_configure_requests,
    run_ok,
    run_ok_bytes,
    seed_matching_lock_sections,
    write_json,
    write_ndjson,
)

SEEDS = [7, 19, 41, 83, 127]

TOP_LEVEL_KEYS = [
    "schema_version",
    "request_rows",
    "declaration_rows",
    "provider_rows",
    "package_selection_rows",
    "target_rows",
    "lock_section_rows",
    "rejection_rows",
    "summary",
]

REQUEST_ROW_KEYS = {
    "configure_request_id",
    "request_index",
    "project_id",
    "provider_config_id",
    "lock_mode",
    "action",
    "resolved_dependency_count",
    "reused_section_count",
    "updated_section_count",
}
DECLARATION_ROW_KEYS = {
    "declaration_id",
    "project_id",
    "dependency_name",
    "declaration_index",
    "ownership",
    "override_find_package",
    "find_package_args_enabled",
}
PROVIDER_ROW_KEYS = {
    "configure_request_id",
    "find_request_id",
    "dependency_name",
    "intercepted",
    "bypass_provider",
    "response_id_or_null",
    "satisfies_or_null",
    "outcome",
}
PACKAGE_SELECTION_ROW_KEYS = {
    "configure_request_id",
    "find_request_id",
    "dependency_name",
    "source_kind",
    "identity_or_null",
    "version_or_null",
    "components",
}
TARGET_ROW_KEYS = {
    "configure_request_id",
    "dependency_name",
    "target_id",
    "role",
    "producer_dependency",
}
LOCK_SECTION_ROW_KEYS = {
    "configure_request_id",
    "dependency_name",
    "section",
    "input_digest",
    "result_digest",
    "disposition",
}
REJECTION_ROW_KEYS = {
    "configure_request_id",
    "find_request_id_or_null",
    "reason_token",
    "message",
}
SUMMARY_KEYS = {
    "configure_request_count",
    "reuse_count",
    "update_count",
    "reject_count",
    "declaration_owner_count",
    "target_row_count",
}
SECTION_ORDER = {
    "declaration": 0,
    "provider": 1,
    "package_selection": 2,
    "target_graph": 3,
    "final_resolution": 4,
}


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path


def _report_path(out_dir: Path) -> Path:
    return out_dir / "resolution_report.json"


def _assert_fatal_case(
    tmp_path: Path,
    out_dir: Path,
    *,
    case_name: str,
    expected_token: str,
    mutate,
) -> None:
    """Copy public fixtures, apply one mutation, and assert a whole-run fatal."""
    data_dir = copy_data_dir(tmp_path / f"fatal-{case_name}")
    mutate(data_dir)
    report_out = _report_path(out_dir / case_name)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_bytes(b"{stale-placeholder}")
    (report_out.parent / "resolution_report.json.tmp").write_text(
        "partial", encoding="utf-8"
    )
    assert_fatal(data_dir, report_out, expected_token)


def _package_row(report: dict, configure_request_id: str, find_request_id: str) -> dict:
    for row in report["package_selection_rows"]:
        if (
            row["configure_request_id"] == configure_request_id
            and row["find_request_id"] == find_request_id
        ):
            return row
    raise AssertionError(f"missing package row {configure_request_id}/{find_request_id}")


def _provider_row(report: dict, configure_request_id: str, find_request_id: str) -> dict:
    for row in report["provider_rows"]:
        if (
            row["configure_request_id"] == configure_request_id
            and row["find_request_id"] == find_request_id
        ):
            return row
    raise AssertionError(f"missing provider row {configure_request_id}/{find_request_id}")


def _request_row(report: dict, configure_request_id: str) -> dict:
    for row in report["request_rows"]:
        if row["configure_request_id"] == configure_request_id:
            return row
    raise AssertionError(configure_request_id)


def _lock_rows(
    report: dict, configure_request_id: str, dependency_name: str
) -> list[dict]:
    return [
        row
        for row in report["lock_section_rows"]
        if row["configure_request_id"] == configure_request_id
        and row["dependency_name"] == dependency_name
    ]


def _target_ids(report: dict, configure_request_id: str, dependency_name: str) -> set[str]:
    return {
        row["target_id"]
        for row in report["target_rows"]
        if row["configure_request_id"] == configure_request_id
        and row["dependency_name"] == dependency_name
    }


def _shuffle_declarations(data_dir: Path, seed: int) -> None:
    doc = read_json(data_dir / "declarations.json")
    decls = doc["declarations"]
    random.Random(seed).shuffle(decls)
    doc["declarations"] = decls
    write_json(data_dir / "declarations.json", doc)


def _first_diff_offset(actual: bytes, expected: bytes) -> int:
    limit = min(len(actual), len(expected))
    for idx in range(limit):
        if actual[idx] != expected[idx]:
            return idx
    return limit


def _assert_exact_key_set(obj: dict[str, Any], required: set[str], label: str) -> None:
    actual = set(obj.keys())
    assert actual == required, (
        f"{label} key set mismatch: actual={sorted(actual)} expected={sorted(required)}"
    )


def _assert_sorted(rows: list[dict[str, Any]], key_fn, label: str) -> None:
    for idx in range(len(rows) - 1):
        left = key_fn(rows[idx])
        right = key_fn(rows[idx + 1])
        assert left <= right, (
            f"{label} out of order at pair {idx}/{idx + 1}: {left!r} then {right!r}"
        )


def _assert_report_contract(raw_bytes: bytes) -> dict[str, Any]:
    """Verify the public report-byte contract without golden or reference loads."""
    assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM is not permitted"
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"report is not valid UTF-8: {exc}") from exc

    assert b"\r" not in raw_bytes, "CRLF structural formatting is not permitted"
    assert b"\t" not in raw_bytes, "tab indentation is not permitted"
    for line in text.split("\n"):
        assert line == line.rstrip(" "), (
            f"trailing spaces are not permitted: {line!r}"
        )

    assert raw_bytes.endswith(b"\n"), (
        f"report must end with exactly one LF; trailing={raw_bytes[-8:]!r}"
    )
    assert not raw_bytes.endswith(b"\n\n"), (
        f"report must not end with multiple LF bytes; trailing={raw_bytes[-8:]!r}"
    )

    report = json.loads(text)
    assert isinstance(report, dict), "root value must be a JSON object"
    actual_keys = list(report.keys())
    assert actual_keys == TOP_LEVEL_KEYS, (
        f"top-level key mismatch: actual={actual_keys} expected={TOP_LEVEL_KEYS}"
    )

    schema_version = report["schema_version"]
    assert type(schema_version) is int, (
        f"schema_version must be int, got {type(schema_version).__name__}={schema_version!r}"
    )
    assert schema_version == 1, f"schema_version must be 1, got {schema_version!r}"

    for section in TOP_LEVEL_KEYS[1:-1]:
        assert isinstance(report[section], list), f"{section} must be a list"
    assert isinstance(report["summary"], dict), "summary must be an object"

    rendered = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if rendered != raw_bytes:
        offset = _first_diff_offset(raw_bytes, rendered)
        raise AssertionError(
            "report bytes do not match the two-space pretty JSON profile; "
            f"first differing byte offset={offset}"
        )

    _assert_sorted(
        report["request_rows"],
        lambda row: row["request_index"],
        "request_rows",
    )
    _assert_sorted(
        report["declaration_rows"],
        lambda row: (row["project_id"], row["declaration_index"], row["declaration_id"]),
        "declaration_rows",
    )
    _assert_sorted(
        report["provider_rows"],
        lambda row: (row["configure_request_id"], row["find_request_id"]),
        "provider_rows",
    )
    _assert_sorted(
        report["package_selection_rows"],
        lambda row: (row["configure_request_id"], row["find_request_id"]),
        "package_selection_rows",
    )
    _assert_sorted(
        report["target_rows"],
        lambda row: (
            row["configure_request_id"],
            row["dependency_name"],
            row["target_id"],
        ),
        "target_rows",
    )
    _assert_sorted(
        report["lock_section_rows"],
        lambda row: (
            row["configure_request_id"],
            row["dependency_name"],
            SECTION_ORDER[row["section"]],
        ),
        "lock_section_rows",
    )
    _assert_sorted(
        report["rejection_rows"],
        lambda row: (
            row["configure_request_id"],
            row["find_request_id_or_null"] or "",
            row["reason_token"],
        ),
        "rejection_rows",
    )

    for row in report["request_rows"]:
        _assert_exact_key_set(row, REQUEST_ROW_KEYS, "request_row")
    for row in report["declaration_rows"]:
        _assert_exact_key_set(row, DECLARATION_ROW_KEYS, "declaration_row")
    for row in report["provider_rows"]:
        _assert_exact_key_set(row, PROVIDER_ROW_KEYS, "provider_row")
    for row in report["package_selection_rows"]:
        _assert_exact_key_set(row, PACKAGE_SELECTION_ROW_KEYS, "package_selection_row")
    for row in report["target_rows"]:
        _assert_exact_key_set(row, TARGET_ROW_KEYS, "target_row")
    for row in report["lock_section_rows"]:
        _assert_exact_key_set(row, LOCK_SECTION_ROW_KEYS, "lock_section_row")
    for row in report["rejection_rows"]:
        _assert_exact_key_set(row, REJECTION_ROW_KEYS, "rejection_row")
    _assert_exact_key_set(report["summary"], SUMMARY_KEYS, "summary")
    return report


def test_01_locked_offline_native_rust_build(out_dir: Path):
    """Release binary exists and is executable; missing required inputs trigger
    a whole-run fatal without writing a report or temp sibling."""
    assert binary_ready(), f"missing candidate binary at {CANDIDATE_BIN}"
    empty = out_dir / "empty_data"
    empty.mkdir()
    report_out = _report_path(out_dir)
    assert_fatal(empty, report_out, "missing_required_input")
    assert not report_out.exists()
    assert not report_out.with_name(report_out.name + ".tmp").exists()


def test_02_cli_required_inputs_and_fatal_cleanup(tmp_path: Path, out_dir: Path):
    """Public loader, schema, reference, and fatal-cleanup contract: missing
    required inputs, malformed JSON/NDJSON, invalid input schema, and unknown
    references each emit the documented whole-run token and remove stale
    report outputs."""
    # Subcase A — missing required input
    data_dir = copy_data_dir(tmp_path / "data")
    (data_dir / "declarations.json").unlink()
    report_out = _report_path(out_dir)
    report_out.write_text("{}", encoding="utf-8")
    (report_out.parent / "resolution_report.json.tmp").write_text(
        "partial", encoding="utf-8"
    )
    assert_fatal(data_dir, report_out, "missing_required_input")

    # Subcase B — malformed ordinary JSON
    def mutate_malformed_json(data: Path) -> None:
        (data / "declarations.json").write_text(
            '{"declarations": [\n', encoding="utf-8"
        )

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="malformed-json",
        expected_token="malformed_json",
        mutate=mutate_malformed_json,
    )

    # Subcase C — malformed NDJSON
    def mutate_malformed_ndjson(data: Path) -> None:
        (data / "find_requests.ndjson").write_text(
            '{"find_request_id":\n', encoding="utf-8"
        )

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="malformed-ndjson",
        expected_token="malformed_json",
        mutate=mutate_malformed_ndjson,
    )

    # Subcase D — invalid input schema (duplicate active normalized overrides)
    def mutate_invalid_schema(data: Path) -> None:
        overrides = read_json(data / "source_overrides.json")
        for override in overrides["overrides"]:
            if override["override_id"] == "ovr-curl-local":
                override["active"] = True
                override["dependency_name"] = "CURL"
            elif override["override_id"] == "ovr-fmt-local":
                override["active"] = True
                override["dependency_name"] = " curl"
        write_json(data / "source_overrides.json", overrides)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="invalid-input-schema",
        expected_token="invalid_input_schema",
        mutate=mutate_invalid_schema,
    )

    # Subcase E — unknown provider reference
    def mutate_unknown_provider(data: Path) -> None:
        policy = read_json(data / "policy.json")
        for cfg in policy["configure_requests"]:
            if cfg["configure_request_id"] == "cfg-root-update":
                cfg["provider_config_id"] = "prov-missing"
                break
        write_json(data / "policy.json", policy)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="unknown-provider",
        expected_token="unknown_reference",
        mutate=mutate_unknown_provider,
    )

    # Subcase F — unknown previous lock reference
    def mutate_unknown_lock(data: Path) -> None:
        policy = read_json(data / "policy.json")
        for cfg in policy["configure_requests"]:
            if cfg["configure_request_id"] == "cfg-root-update":
                cfg["previous_lock_id_or_null"] = "lock-missing"
                break
        write_json(data / "policy.json", policy)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="unknown-lock",
        expected_token="unknown_reference",
        mutate=mutate_unknown_lock,
    )

    # Subcase G — unknown find-request reference
    def mutate_unknown_find(data: Path) -> None:
        policy = read_json(data / "policy.json")
        for cfg in policy["configure_requests"]:
            if cfg["configure_request_id"] == "cfg-root-update":
                cfg["find_request_ids"].append("freq-missing")
                break
        write_json(data / "policy.json", policy)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="unknown-find",
        expected_token="unknown_reference",
        mutate=mutate_unknown_find,
    )


def test_03_declaration_first_call_controls(tmp_path: Path, out_dir: Path):
    """The first declaration in chronology owns a dependency name; a later
    shadowed declaration with conflicting flags does not change resolution."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    zlib_decl = [
        row
        for row in report["declaration_rows"]
        if row["project_id"] == "root" and row["dependency_name"] == "zlib"
    ]
    owners = [row for row in zlib_decl if row["ownership"] == "owner"]
    shadowed = [row for row in zlib_decl if row["ownership"] == "shadowed"]
    assert len(owners) == 1 and owners[0]["declaration_id"] == "decl-zlib-root"
    assert len(shadowed) == 1 and shadowed[0]["declaration_id"] == "decl-zlib-shadow"
  # shadowed row would redirect to FetchContent if it owned the name
    pkg = _package_row(report, "cfg-root-update", "freq-zlib")
    assert pkg["source_kind"] == "provider"
    assert pkg["identity_or_null"] == "resp-zlib-provide"


def test_04_declaration_chronology_ignores_physical_order(
    tmp_path: Path, out_dir: Path
):
    """Permuting physical ``declarations.json`` order does not change parsed
    report semantics for the root configure request. Duplicate public indexes
    remain whole-run fatals with stale output cleanup."""
    baseline_dir = copy_data_dir(tmp_path / "baseline")
    restrict_configure_requests(baseline_dir, ["cfg-root-update"])
    baseline = run_ok(baseline_dir, _report_path(out_dir / "a"))
    for seed in SEEDS[:3]:
        mutated = copy_data_dir(tmp_path / f"perm-{seed}")
        restrict_configure_requests(mutated, ["cfg-root-update"])
        _shuffle_declarations(mutated, seed)
        actual = run_ok(mutated, _report_path(out_dir / f"b-{seed}"))
        assert actual["package_selection_rows"] == baseline["package_selection_rows"]
        assert actual["provider_rows"] == baseline["provider_rows"]
        assert actual["target_rows"] == baseline["target_rows"]

    # Subcase A — duplicate declaration index within one project
    def mutate_dup_decl_index(data: Path) -> None:
        decls = read_json(data / "declarations.json")
        zlib_index = None
        for decl in decls["declarations"]:
            if decl["declaration_id"] == "decl-zlib-root":
                zlib_index = decl["declaration_index"]
                break
        assert zlib_index is not None
        for decl in decls["declarations"]:
            if decl["declaration_id"] == "decl-openssl-root":
                decl["declaration_index"] = zlib_index
                break
        write_json(data / "declarations.json", decls)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="dup-decl-index",
        expected_token="duplicate_declaration_index",
        mutate=mutate_dup_decl_index,
    )

    # Subcase B — duplicate find request index within one project
    def mutate_dup_find_index(data: Path) -> None:
        rows = read_ndjson(data / "find_requests.ndjson")
        zlib_index = None
        for row in rows:
            if row["find_request_id"] == "freq-zlib":
                zlib_index = row["request_index"]
                break
        assert zlib_index is not None
        for row in rows:
            if row["find_request_id"] == "freq-openssl":
                row["request_index"] = zlib_index
                break
        write_ndjson(data / "find_requests.ndjson", rows)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="dup-find-index",
        expected_token="duplicate_find_request_index",
        mutate=mutate_dup_find_index,
    )

    # Subcase C — duplicate configure request index
    def mutate_dup_cfg_index(data: Path) -> None:
        policy = read_json(data / "policy.json")
        update_index = None
        for cfg in policy["configure_requests"]:
            if cfg["configure_request_id"] == "cfg-root-update":
                update_index = cfg["request_index"]
                break
        assert update_index is not None
        for cfg in policy["configure_requests"]:
            if cfg["configure_request_id"] == "cfg-root-error":
                cfg["request_index"] = update_index
                break
        write_json(data / "policy.json", policy)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="dup-cfg-index",
        expected_token="duplicate_configure_request_index",
        mutate=mutate_dup_cfg_index,
    )


def test_05_provider_intercepts_direct_find_package(tmp_path: Path, out_dir: Path):
    """With default provider interception, ``find_package`` resolves from the
  provider when a satisfying response exists."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    prov = _provider_row(report, "cfg-root-update", "freq-fmt")
    pkg = _package_row(report, "cfg-root-update", "freq-fmt")
    assert prov["intercepted"] is True
    assert prov["outcome"] == "provider_resolved"
    assert pkg["source_kind"] == "provider"
    assert pkg["identity_or_null"] == "resp-fmt-provide"


def test_06_bypass_provider_uses_builtin_selection(tmp_path: Path, out_dir: Path):
    """``bypass_provider`` skips interception and falls through to package
    candidate selection."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    prov = _provider_row(report, "cfg-root-update", "freq-curl")
    pkg = _package_row(report, "cfg-root-update", "freq-curl")
    assert prov["bypass_provider"] is True
    assert prov["intercepted"] is False
    assert prov["outcome"] == "provider_skipped"
    assert pkg["source_kind"] == "package"
    assert pkg["identity_or_null"] == "pkg-curl-alt"


def test_07_explicit_source_override_suppresses_provider(
    tmp_path: Path, out_dir: Path
):
    """An active source-directory override suppresses provider interception and
    becomes the resolution source."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    overrides = read_json(data_dir / "source_overrides.json")
    for override in overrides["overrides"]:
        if override["override_id"] == "ovr-curl-local":
            override["active"] = True
    write_json(data_dir / "source_overrides.json", overrides)
    report = run_ok(data_dir, _report_path(out_dir))
    prov = _provider_row(report, "cfg-root-update", "freq-curl")
    pkg = _package_row(report, "cfg-root-update", "freq-curl")
    assert prov["intercepted"] is False
    assert prov["outcome"] == "provider_skipped"
    assert pkg["source_kind"] == "override"
    assert pkg["identity_or_null"] == "ovr-curl-local"


def test_08_override_find_package_redirects_later_requests(
    tmp_path: Path, out_dir: Path
):
    """When the owning declaration sets ``override_find_package``, package
    candidates are not searched even if present."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    pkg = _package_row(report, "cfg-root-update", "freq-openssl")
    prov = _provider_row(report, "cfg-root-update", "freq-openssl")
    assert prov["outcome"] == "provider_resolved"
    assert pkg["source_kind"] == "provider"
    assert pkg["identity_or_null"] == "resp-openssl-provide"


def test_09_find_package_args_try_system_first(tmp_path: Path, out_dir: Path):
    """For ``find_package`` with interception disabled and ``try_system_first``,
    a matching system package candidate is chosen before FetchContent fallback."""
    data_dir = copy_data_dir(tmp_path / "data")
    policy = read_json(data_dir / "policy.json")
    policy["configure_requests"] = [
        {
            "configure_request_id": "cfg-zlib-system",
            "request_index": 1,
            "project_id": "root",
            "provider_config_id": "prov-off",
            "lock_mode": "update",
            "previous_lock_id_or_null": None,
            "find_request_ids": ["freq-zlib"],
        }
    ]
    write_json(data_dir / "policy.json", policy)
    requests = read_ndjson(data_dir / "find_requests.ndjson")
    for row in requests:
        if row["find_request_id"] == "freq-zlib":
            row["version_or_null"] = "1.3.1"
            row["exact"] = True
    write_ndjson(data_dir / "find_requests.ndjson", requests)
    candidates = read_json(data_dir / "package_candidates.json")
    candidates["candidates"] = [
        row for row in candidates["candidates"] if row["candidate_id"] != "pkg-zlib-old"
    ]
    write_json(data_dir / "package_candidates.json", candidates)
    report = run_ok(data_dir, _report_path(out_dir))
    pkg = _package_row(report, "cfg-zlib-system", "freq-zlib")
    assert pkg["source_kind"] == "package"
    assert pkg["identity_or_null"] == "pkg-zlib-system"


def test_10_override_and_find_args_conflict_is_fatal(tmp_path: Path, out_dir: Path):
    """Owning declaration with both ``override_find_package`` and enabled
    ``find_package_args`` is a whole-run fatal."""
    data_dir = copy_data_dir(tmp_path / "data")
    decls = read_json(data_dir / "declarations.json")
    for decl in decls["declarations"]:
        if decl["declaration_id"] == "decl-zlib-root":
            decl["override_find_package"] = True
            decl["find_package_args"]["enabled"] = True
    write_json(data_dir / "declarations.json", decls)
    assert_fatal(data_dir, _report_path(out_dir), "conflicting_declaration_flags")


def _rejection_rows_for(
    report: dict, configure_request_id: str, find_request_id: str | None = None
) -> list[dict]:
    rows = [
        row
        for row in report["rejection_rows"]
        if row["configure_request_id"] == configure_request_id
    ]
    if find_request_id is None:
        return rows
    return [row for row in rows if row.get("find_request_id_or_null") == find_request_id]


def test_11_required_and_optional_request_behavior(tmp_path: Path, out_dir: Path):
    """Required unresolved dependencies reject a configure request while
    optional ones emit ``not_found`` yet the overall run still exits zero."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    optional = _package_row(report, "cfg-root-update", "freq-json-opt")
    optional_rejections = _rejection_rows_for(report, "cfg-root-update", "freq-json-opt")
    cfg_action = _request_row(report, "cfg-root-update")["action"]
    assert optional["source_kind"] == "not_found", (
        "optional unresolved contract failed: "
        f"find_request_id=freq-json-opt required=false "
        f"package_selection_row={optional!r} "
        f"matching_rejection_rows={optional_rejections!r} "
        f"configure_action={cfg_action!r}"
    )
    assert optional_rejections == [], (
        "optional unresolved must not emit a rejection row: "
        f"find_request_id=freq-json-opt required=false "
        f"package_selection_row={optional!r} "
        f"matching_rejection_rows={optional_rejections!r} "
        f"configure_action={cfg_action!r}"
    )
    assert cfg_action == "update_resolution", (
        "optional unresolved must not reject configure solely for that dependency: "
        f"find_request_id=freq-json-opt required=false "
        f"package_selection_row={optional!r} "
        f"matching_rejection_rows={optional_rejections!r} "
        f"configure_action={cfg_action!r}"
    )
    data_dir2 = copy_data_dir(tmp_path / "data-required-fail")
    policy = read_json(data_dir2 / "policy.json")
    policy["configure_requests"] = [
        {
            "configure_request_id": "cfg-fmt-fail",
            "request_index": 1,
            "project_id": "root",
            "provider_config_id": "prov-off",
            "lock_mode": "update",
            "previous_lock_id_or_null": None,
            "find_request_ids": ["freq-fmt"],
        }
    ]
    write_json(data_dir2 / "policy.json", policy)
    providers = read_json(data_dir2 / "provider_responses.json")
    providers["responses"] = [
        row for row in providers["responses"] if row["response_id"] != "resp-fmt-provide"
    ]
    write_json(data_dir2 / "provider_responses.json", providers)
    candidates = read_json(data_dir2 / "package_candidates.json")
    candidates["candidates"] = [
        row for row in candidates["candidates"] if row["dependency_name"].lower() != "fmt"
    ]
    write_json(data_dir2 / "package_candidates.json", candidates)
    requests = read_ndjson(data_dir2 / "find_requests.ndjson")
    for row in requests:
        if row["find_request_id"] == "freq-fmt":
            row["version_or_null"] = "99.9.9"
            row["exact"] = True
    write_ndjson(data_dir2 / "find_requests.ndjson", requests)
    report2 = run_ok(data_dir2, _report_path(out_dir / "required"))
    required_pkg = _package_row(report2, "cfg-fmt-fail", "freq-fmt")
    required_rejections = _rejection_rows_for(report2, "cfg-fmt-fail", "freq-fmt")
    required_action = _request_row(report2, "cfg-fmt-fail")["action"]
    assert required_pkg["source_kind"] == "not_found", (
        "required unresolved must emit not_found package row: "
        f"find_request_id=freq-fmt required=true "
        f"package_selection_row={required_pkg!r} "
        f"matching_rejection_rows={required_rejections!r} "
        f"configure_action={required_action!r}"
    )
    assert required_action == "reject_configuration", (
        "required unresolved must reject configure: "
        f"find_request_id=freq-fmt required=true "
        f"package_selection_row={required_pkg!r} "
        f"matching_rejection_rows={required_rejections!r} "
        f"configure_action={required_action!r}"
    )
    assert any(
        row["reason_token"] in {"unresolved_dependency", "version_mismatch"}
        for row in required_rejections
    ), (
        "required unresolved must emit one terminal rejection: "
        f"find_request_id=freq-fmt required=true "
        f"package_selection_row={required_pkg!r} "
        f"matching_rejection_rows={required_rejections!r} "
        f"configure_action={required_action!r}"
    )


def test_12_exact_and_minimum_version_matching(tmp_path: Path, out_dir: Path):
    """Exact requests require equality; minimum requests accept compatible
    newer candidates."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    openssl = _package_row(report, "cfg-root-update", "freq-openssl")
    curl = _package_row(report, "cfg-root-update", "freq-curl")
    assert openssl["version_or_null"] == "3.0.13"
    assert curl["source_kind"] == "package"
    assert curl["version_or_null"] == "8.6.0"
    data_dir2 = copy_data_dir(tmp_path / "data-version-fail")
    policy = read_json(data_dir2 / "policy.json")
    policy["configure_requests"] = [
        {
            "configure_request_id": "cfg-openssl-exact-fail",
            "request_index": 1,
            "project_id": "root",
            "provider_config_id": "prov-default",
            "lock_mode": "update",
            "previous_lock_id_or_null": None,
            "find_request_ids": ["freq-openssl"],
        }
    ]
    write_json(data_dir2 / "policy.json", policy)
    providers = read_json(data_dir2 / "provider_responses.json")
    attempted_provider_version = None
    for response in providers["responses"]:
        if response["response_id"] == "resp-openssl-provide":
            attempted_provider_version = response.get("version_or_null")
            response["satisfies"] = False
    write_json(data_dir2 / "provider_responses.json", providers)
    requests = read_ndjson(data_dir2 / "find_requests.ndjson")
    request_version = None
    request_exact = None
    for row in requests:
        if row["find_request_id"] == "freq-openssl":
            row["version_or_null"] = "9.9.9"
            request_version = row["version_or_null"]
            request_exact = row.get("exact", False)
    write_ndjson(data_dir2 / "find_requests.ndjson", requests)
    decls = read_json(data_dir2 / "declarations.json")
    attempted_fallback_version = None
    for decl in decls["declarations"]:
        if decl.get("dependency_name", "").lower() == "openssl":
            attempted_fallback_version = decl.get("declared_version_or_null")
            break
    report2 = run_ok(data_dir2, _report_path(out_dir / "ver"))
    selected = _package_row(report2, "cfg-openssl-exact-fail", "freq-openssl")
    matching_rejections = _rejection_rows_for(
        report2, "cfg-openssl-exact-fail", "freq-openssl"
    )
    action = _request_row(report2, "cfg-openssl-exact-fail")["action"]
    assert selected["source_kind"] == "not_found", (
        "version failure contract: "
        f"request_version={request_version!r} exact={request_exact!r} "
        f"attempted_provider_version={attempted_provider_version!r} "
        f"attempted_fallback_version={attempted_fallback_version!r} "
        f"selected_source_row={selected!r} "
        f"matching_rejection_rows={matching_rejections!r}"
    )
    assert action == "reject_configuration", (
        "version failure must reject configure: "
        f"request_version={request_version!r} exact={request_exact!r} "
        f"attempted_provider_version={attempted_provider_version!r} "
        f"attempted_fallback_version={attempted_fallback_version!r} "
        f"selected_source_row={selected!r} "
        f"matching_rejection_rows={matching_rejections!r}"
    )
    assert any(row["reason_token"] == "version_mismatch" for row in matching_rejections), (
        "version failure must emit version_mismatch: "
        f"request_version={request_version!r} exact={request_exact!r} "
        f"attempted_provider_version={attempted_provider_version!r} "
        f"attempted_fallback_version={attempted_fallback_version!r} "
        f"selected_source_row={selected!r} "
        f"matching_rejection_rows={matching_rejections!r}"
    )

    # Whole-run fatal: version string outside the bounded grammar
    def mutate_invalid_version(data: Path) -> None:
        rows = read_ndjson(data / "find_requests.ndjson")
        for row in rows:
            if row["find_request_id"] == "freq-openssl":
                row["version_or_null"] = "1.2.3.4"
                break
        write_ndjson(data / "find_requests.ndjson", rows)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="invalid-version",
        expected_token="invalid_version",
        mutate=mutate_invalid_version,
    )


def test_13_component_requirements_are_complete_sets(tmp_path: Path, out_dir: Path):
    """Every requested component must be provided by the chosen source."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    openssl = _package_row(report, "cfg-root-update", "freq-openssl")
    assert sorted(openssl["components"]) == ["Crypto", "SSL"]
    data_dir2 = copy_data_dir(tmp_path / "data-components-fail")
    policy = read_json(data_dir2 / "policy.json")
    policy["configure_requests"] = [
        {
            "configure_request_id": "cfg-openssl-components",
            "request_index": 1,
            "project_id": "root",
            "provider_config_id": "prov-default",
            "lock_mode": "update",
            "previous_lock_id_or_null": None,
            "find_request_ids": ["freq-openssl"],
        }
    ]
    write_json(data_dir2 / "policy.json", policy)
    providers = read_json(data_dir2 / "provider_responses.json")
    provider_components = None
    for response in providers["responses"]:
        if response["response_id"] == "resp-openssl-provide":
            response["provided_components"] = ["SSL"]
            provider_components = list(response["provided_components"])
    write_json(data_dir2 / "provider_responses.json", providers)
    requests = read_ndjson(data_dir2 / "find_requests.ndjson")
    requested_components = None
    for row in requests:
        if row["find_request_id"] == "freq-openssl":
            requested_components = sorted(set(row.get("components", [])))
            break
    fallback_projection = ["default"]
    report2 = run_ok(data_dir2, _report_path(out_dir / "comp"))
    selected = _package_row(report2, "cfg-openssl-components", "freq-openssl")
    matching_rejections = _rejection_rows_for(
        report2, "cfg-openssl-components", "freq-openssl"
    )
    action = _request_row(report2, "cfg-openssl-components")["action"]
    assert selected["source_kind"] == "not_found", (
        "component failure contract: "
        f"requested_components={requested_components!r} "
        f"provider_provided_components={provider_components!r} "
        f"fallback_component_projection={fallback_projection!r} "
        f"selected_source_row={selected!r} "
        f"matching_rejection_rows={matching_rejections!r}"
    )
    assert action == "reject_configuration", (
        "component failure must reject configure: "
        f"requested_components={requested_components!r} "
        f"provider_provided_components={provider_components!r} "
        f"fallback_component_projection={fallback_projection!r} "
        f"selected_source_row={selected!r} "
        f"matching_rejection_rows={matching_rejections!r}"
    )
    assert any(
        row["reason_token"] == "components_unsatisfied" for row in matching_rejections
    ), (
        "component failure must emit components_unsatisfied: "
        f"requested_components={requested_components!r} "
        f"provider_provided_components={provider_components!r} "
        f"fallback_component_projection={fallback_projection!r} "
        f"selected_source_row={selected!r} "
        f"matching_rejection_rows={matching_rejections!r}"
    )


def test_14_provider_result_target_validation(tmp_path: Path, out_dir: Path):
    """Provider-produced targets are validated and expanded through the target
    graph closure."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    targets = _target_ids(report, "cfg-root-update", "fmt")
    assert "fmt::fmt" in targets
    spdlog_targets = _target_ids(report, "cfg-root-update", "spdlog")
    assert "spdlog::spdlog" in spdlog_targets
    assert "fmt::fmt" in spdlog_targets


def test_15_fetchcontent_fallback_selection(tmp_path: Path, out_dir: Path):
    """When the provider declines, resolution falls back to the owning FetchContent
    declaration."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-net-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    grpc = _package_row(report, "cfg-net-update", "freq-grpc")
    assert grpc["source_kind"] == "fetchcontent"
    assert grpc["identity_or_null"] == "decl-grpc-net"


def test_16_duplicate_target_producer_is_fatal(tmp_path: Path, out_dir: Path):
    """Two dependencies producing the same target in one configure request is a
    whole-run fatal."""
    data_dir = copy_data_dir(tmp_path / "data")
    policy = read_json(data_dir / "policy.json")
    policy["configure_requests"] = [
        {
            "configure_request_id": "cfg-dup-target",
            "request_index": 1,
            "project_id": "root",
            "provider_config_id": "prov-default",
            "lock_mode": "update",
            "previous_lock_id_or_null": None,
            "find_request_ids": ["freq-fmt", "freq-openssl"],
        }
    ]
    write_json(data_dir / "policy.json", policy)
    providers = read_json(data_dir / "provider_responses.json")
    for response in providers["responses"]:
        if response["response_id"] == "resp-openssl-provide":
            response["produced_targets"] = ["OpenSSL::SSL", "OpenSSL::Crypto", "fmt::fmt"]
    write_json(data_dir / "provider_responses.json", providers)
    assert_fatal(data_dir, _report_path(out_dir), "duplicate_target_producer")


def test_17_target_dependency_transitive_closure(tmp_path: Path, out_dir: Path):
    """Resolved root targets include transitive dependencies from the graph."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    report = run_ok(data_dir, _report_path(out_dir))
    curl_targets = _target_ids(report, "cfg-root-update", "curl")
    assert {
        "CURL::libcurl",
        "ZLIB::ZLIB",
        "OpenSSL::SSL",
        "OpenSSL::Crypto",
    }.issubset(curl_targets)


def test_18_target_dependency_cycle_is_fatal(tmp_path: Path, out_dir: Path):
    """Unknown reachable target endpoints and missing produced root targets are
    whole-run fatals; a directed dependency cycle inside a configure-request
    closure is also fatal."""

    # Subcase A — unknown closure edge endpoint
    def mutate_unknown_edge(data: Path) -> None:
        policy = read_json(data / "policy.json")
        policy["configure_requests"] = [
            {
                "configure_request_id": "cfg-unknown-edge",
                "request_index": 1,
                "project_id": "root",
                "provider_config_id": "prov-default",
                "lock_mode": "update",
                "previous_lock_id_or_null": None,
                "find_request_ids": ["freq-curl"],
            }
        ]
        write_json(data / "policy.json", policy)
        graph = read_json(data / "target_graph.json")
        graph["edges"].append(
            {"from_target": "CURL::libcurl", "to_target": "Missing::Target"}
        )
        write_json(data / "target_graph.json", graph)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="unknown-edge",
        expected_token="unknown_target_reference",
        mutate=mutate_unknown_edge,
    )

    # Subcase B — produced root target missing from target catalogue
    def mutate_missing_root_target(data: Path) -> None:
        policy = read_json(data / "policy.json")
        policy["configure_requests"] = [
            {
                "configure_request_id": "cfg-missing-root-target",
                "request_index": 1,
                "project_id": "root",
                "provider_config_id": "prov-default",
                "lock_mode": "update",
                "previous_lock_id_or_null": None,
                "find_request_ids": ["freq-curl"],
            }
        ]
        write_json(data / "policy.json", policy)
        graph = read_json(data / "target_graph.json")
        graph["targets"] = [
            target
            for target in graph["targets"]
            if target["target_id"] != "CURL::libcurl"
        ]
        write_json(data / "target_graph.json", graph)

    _assert_fatal_case(
        tmp_path,
        out_dir,
        case_name="missing-root-target",
        expected_token="unknown_target_reference",
        mutate=mutate_missing_root_target,
    )

    # Existing cycle subcase
    data_dir = copy_data_dir(tmp_path / "data")
    policy = read_json(data_dir / "policy.json")
    policy["configure_requests"] = [
        {
            "configure_request_id": "cfg-cycle",
            "request_index": 1,
            "project_id": "root",
            "provider_config_id": "prov-default",
            "lock_mode": "update",
            "previous_lock_id_or_null": None,
            "find_request_ids": ["freq-curl"],
        }
    ]
    write_json(data_dir / "policy.json", policy)
    graph = read_json(data_dir / "target_graph.json")
    graph["edges"].append({"from_target": "ZLIB::ZLIB", "to_target": "CURL::libcurl"})
    write_json(data_dir / "target_graph.json", graph)
    assert_fatal(data_dir, _report_path(out_dir), "target_dependency_cycle")


def test_20_declaration_mutation_invalidates_dependents(tmp_path: Path, out_dir: Path):
    """Mutating a declaration preimage cascades stale status to downstream lock
    sections for that dependency only."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-util-reuse"])
    seed_matching_lock_sections(
        data_dir,
        lock_id="lock-util-v1",
        configure_request_id="cfg-util-reuse",
    )
    decls = read_json(data_dir / "declarations.json")
    for decl in decls["declarations"]:
        if decl["declaration_id"] == "decl-fmt-util":
            decl["content_digest"] = "f" * 64
    write_json(data_dir / "declarations.json", decls)
    report = run_ok(data_dir, _report_path(out_dir))
    lock_rows = _lock_rows(report, "cfg-util-reuse", "fmt")
    sections = {row["section"]: row["disposition"] for row in lock_rows}
    assert sections["declaration"] == "updated"
    assert sections["provider"] == "updated"
    assert sections["package_selection"] == "updated"
    assert sections["target_graph"] == "updated"
    assert sections["final_resolution"] == "updated"


def test_22_source_override_mutation_changes_resolution(tmp_path: Path, out_dir: Path):
    """Activating a source override changes package selection away from the
    prior package/provider path."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    before = run_ok(copy_data_dir(tmp_path / "before"), _report_path(out_dir / "before"))
    before_pkg = _package_row(before, "cfg-root-update", "freq-curl")
    overrides = read_json(data_dir / "source_overrides.json")
    for override in overrides["overrides"]:
        if override["override_id"] == "ovr-curl-local":
            override["active"] = True
    write_json(data_dir / "source_overrides.json", overrides)
    after = run_ok(data_dir, _report_path(out_dir / "after"))
    after_pkg = _package_row(after, "cfg-root-update", "freq-curl")
    assert before_pkg["source_kind"] == "package"
    assert after_pkg["source_kind"] == "override"
    assert after_pkg["identity_or_null"] == "ovr-curl-local"


def test_23_error_and_update_lock_modes(tmp_path: Path, out_dir: Path):
    """``error`` lock mode rejects stale sections while ``update`` recomputes
    them and continues."""
    data_dir = copy_data_dir(tmp_path / "data")
    report = run_ok(data_dir, _report_path(out_dir))
    error_row = _request_row(report, "cfg-root-error")
    update_row = _request_row(report, "cfg-root-update")
    assert error_row["lock_mode"] == "error"
    assert error_row["action"] == "reject_configuration"
    assert any(
        row["configure_request_id"] == "cfg-root-error"
        and row["reason_token"] == "stale_lock_section"
        for row in report["rejection_rows"]
    )
    assert update_row["lock_mode"] == "update"
    assert update_row["action"] == "update_resolution"
    assert update_row["updated_section_count"] > 0


def test_24_coupled_provider_override_target_mutation(
    tmp_path: Path, out_dir: Path
):
    """Provider decline plus an active override with extra imported targets
    changes only the mutated dependency's lock sections and target closure."""
    data_dir = copy_data_dir(tmp_path / "data")
    restrict_configure_requests(data_dir, ["cfg-root-update"])
    baseline = run_ok(copy_data_dir(tmp_path / "baseline24"), _report_path(out_dir / "base"))
    fmt_pkg_before = _package_row(baseline, "cfg-root-update", "freq-fmt")
    curl_targets_before = _target_ids(baseline, "cfg-root-update", "curl")
    overrides = read_json(data_dir / "source_overrides.json")
    for override in overrides["overrides"]:
        if override["override_id"] == "ovr-curl-local":
            override["active"] = True
            override["produced_targets"] = ["CURL::libcurl", "CURL::curl_extra"]
    write_json(data_dir / "source_overrides.json", overrides)
    providers = read_json(data_dir / "provider_responses.json")
    for response in providers["responses"]:
        if response["response_id"] == "resp-curl-decline":
            response["satisfies"] = False
    write_json(data_dir / "provider_responses.json", providers)
    mutated = run_ok(data_dir, _report_path(out_dir / "mut"))
    fmt_pkg_after = _package_row(mutated, "cfg-root-update", "freq-fmt")
    assert fmt_pkg_after == fmt_pkg_before
    curl_pkg = _package_row(mutated, "cfg-root-update", "freq-curl")
    assert curl_pkg["source_kind"] == "override"
    curl_targets_after = _target_ids(mutated, "cfg-root-update", "curl")
    assert "CURL::curl_extra" in curl_targets_after
    assert curl_targets_after != curl_targets_before
    curl_locks = _lock_rows(mutated, "cfg-root-update", "curl")
    assert all(row["disposition"] == "updated" for row in curl_locks)
    fmt_locks = _lock_rows(mutated, "cfg-root-update", "fmt")
    baseline_fmt_locks = _lock_rows(baseline, "cfg-root-update", "fmt")
    assert fmt_locks == baseline_fmt_locks


def test_26_permutation_byte_determinism_and_fatal_cleanup(
    tmp_path: Path, out_dir: Path
):
    """Canonical report bytes satisfy the public contract; declaration-order
    permutations stay byte-identical; whole-run fatal deletes report and temp."""
    data_dir = copy_data_dir(tmp_path / "data")
    first_path = _report_path(out_dir / "first")
    first_bytes = run_ok_bytes(data_dir, first_path)
    report = _assert_report_contract(first_bytes)
    assert report["schema_version"] == 1
    assert list(report.keys()) == TOP_LEVEL_KEYS
    assert not first_path.with_name(first_path.name + ".tmp").exists()
    for seed in SEEDS:
        perm_dir = copy_data_dir(tmp_path / f"perm-{seed}")
        _shuffle_declarations(perm_dir, seed)
        perm_bytes = run_ok_bytes(perm_dir, _report_path(out_dir / f"perm-{seed}"))
        assert perm_bytes == first_bytes
    fatal_dir = copy_data_dir(tmp_path / "fatal")
    decls = read_json(fatal_dir / "declarations.json")
    for decl in decls["declarations"]:
        if decl["declaration_id"] == "decl-zlib-root":
            decl["override_find_package"] = True
            decl["find_package_args"]["enabled"] = True
    write_json(fatal_dir / "declarations.json", decls)
    report_out = _report_path(out_dir / "fatal")
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("{}", encoding="utf-8")
    (report_out.parent / "resolution_report.json.tmp").write_text("partial", encoding="utf-8")
    assert_fatal(fatal_dir, report_out, "conflicting_declaration_flags")
    assert not report_out.exists()
    assert not report_out.with_name(report_out.name + ".tmp").exists()
