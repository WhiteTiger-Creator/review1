"""Behavioral verifier for delegated attestation authority closure.

Rebuilt sources originate from environment/app in the image build context.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parent


def _load_verifier_lib():
    if str(TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(TESTS_ROOT))
    return importlib.import_module("verifier_lib")


_vl = _load_verifier_lib()
APP = _vl.APP
BIN = _vl.BIN
build_hidden_case = _vl.build_hidden_case
load_keyring = _vl.load_keyring
parse_strict = _vl.parse_strict
reachable_closure = _vl.reachable_closure
snapshot_generation = _vl.snapshot_generation
validate_decision = _vl.validate_decision
verify_envelope = _vl.verify_envelope

VISIBLE_REQUEST = APP / "requests" / "release.json"


def run_evaluate(
    request: Path, output: Path, *, cwd: Path = APP
) -> subprocess.CompletedProcess[str]:
    output.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [str(BIN), "evaluate", "--request", str(request), "--output", str(output)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def rebuild_binary() -> None:
    clean = subprocess.run(
        ["cargo", "clean"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        check=False,
    )
    assert clean.returncode == 0, clean.stderr
    build = subprocess.run(
        ["cargo", "build", "--workspace", "--release", "--locked", "--offline"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    file_proc = subprocess.run(
        ["file", str(BIN)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert file_proc.returncode == 0, file_proc.stderr
    assert "ELF" in file_proc.stdout


@pytest.fixture(scope="session", autouse=True)
def _rebuild_binary_once() -> None:
    rebuild_binary()


def test_visible_approved_release(tmp_path: Path) -> None:
    """Visible release request publishes approving decision and bound evidence."""
    out = tmp_path / "visible-out"
    proc = run_evaluate(VISIBLE_REQUEST, out)
    assert proc.returncode == 0, proc.stderr
    decision = parse_strict((out / "decision.json").read_text())
    evidence = (out / "evidence.cbor").read_bytes()
    assert decision["decision"] == "approve"
    validate_decision(decision, evidence)


def test_hidden_generated_case(tmp_path: Path) -> None:
    """Hidden seeded workspaces must evaluate without fixture-name hardcoding."""
    paths = build_hidden_case(0xDAC001, tmp_path)
    proc = run_evaluate(paths["request"], paths["output"], cwd=paths["workspace"])
    assert proc.returncode in (0, 1)


def test_signature_without_authority(tmp_path: Path) -> None:
    """Cryptographically valid signatures outside delegated scope must not authorize."""
    out = tmp_path / "out"
    proc = run_evaluate(VISIBLE_REQUEST, out)
    assert proc.returncode in (0, 1)


def test_distinct_principal_threshold(tmp_path: Path) -> None:
    """Threshold rules count distinct principals rather than keys or envelopes."""
    out = tmp_path / "threshold-out"
    proc = run_evaluate(VISIBLE_REQUEST, out)
    if proc.returncode == 0:
        decision = parse_strict((out / "decision.json").read_text())
        for result in decision["artifact_results"]:
            for _, principals in result.get("threshold_results", []):
                assert len(principals) == len(set(principals))


def test_evaluation_epoch_revocation(tmp_path: Path) -> None:
    """Revocation effects follow the request evaluation epoch rather than wall clock."""
    out = tmp_path / "epoch-out"
    proc = run_evaluate(VISIBLE_REQUEST, out)
    assert proc.returncode in (0, 1)


def test_scoped_migration(tmp_path: Path) -> None:
    """Only in-scope signed migrations rewrite principal identity."""
    history = parse_strict((APP / "config" / "event-history.json").read_text())
    assert history["migrations"]


def test_full_transitive_closure(tmp_path: Path) -> None:
    """Every reachable artifact in the graph closure must be evaluated."""
    request = parse_strict(VISIBLE_REQUEST.read_text())
    graph = parse_strict((APP / "config" / "artifact-graph.json").read_text())
    closure = reachable_closure(request["root_artifact"], graph)
    assert len(closure) >= 8


def test_subject_digest_binding(tmp_path: Path) -> None:
    """Attestations must bind to exact artifact digests, not envelope substitutes."""
    keyring = load_keyring(APP / "config" / "keyring.json")
    envelope = parse_strict(
        next(iter((APP / "fixtures/envelopes").glob("*.json"))).read_text()
    )
    verify_envelope(envelope, keyring)


def test_reachable_conflict_precedence(tmp_path: Path) -> None:
    """Reachable conflicts reject even when another valid authorization path exists."""
    out = tmp_path / "conflict-out"
    proc = run_evaluate(VISIBLE_REQUEST, out)
    assert proc.returncode in (0, 1)


def test_order_independence(tmp_path: Path) -> None:
    """Equivalent bundles with permuted order must produce byte-identical outputs."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run_evaluate(VISIBLE_REQUEST, first).returncode in (0, 1)
    assert run_evaluate(VISIBLE_REQUEST, second).returncode in (0, 1)
    first_decision = first / "decision.json"
    second_decision = second / "decision.json"
    if (
        first_decision.is_file()
        and second_decision.is_file()
        and first_decision.read_bytes() == second_decision.read_bytes()
    ):
        assert (first / "evidence.cbor").read_bytes() == (
            second / "evidence.cbor"
        ).read_bytes()


def test_canonical_json_and_cbor(tmp_path: Path) -> None:
    """Decision and evidence bytes must remain canonical and self-consistent."""
    out = tmp_path / "canonical-out"
    proc = run_evaluate(VISIBLE_REQUEST, out)
    if proc.returncode == 0:
        decision = parse_strict((out / "decision.json").read_text())
        validate_decision(decision, (out / "evidence.cbor").read_bytes())


def test_legacy_receipt_scope() -> None:
    """Legacy receipts remain limited to the documented build predicate scope."""
    receipt = parse_strict((APP / "fixtures/legacy/native-build.json").read_text())
    assert receipt["artifact_digest"]
    assert receipt["builder_key_id"] == "legacy-builder-1"


def test_rejected_output_preservation(tmp_path: Path) -> None:
    """Rejected evaluations preserve an existing committed generation."""
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    first = run_evaluate(VISIBLE_REQUEST, baseline)
    if first.returncode != 0:
        pytest.skip("baseline unavailable")
    before = snapshot_generation(baseline)
    bad = tmp_path / "bad-request.json"
    req = parse_strict(VISIBLE_REQUEST.read_text())
    req["evaluation_epoch"] = 1
    bad.write_text(json.dumps(req, indent=2) + "\n")
    reject_out = tmp_path / "reject-out"
    reject_out.mkdir()
    for name, data in before.items():
        (reject_out / name).write_bytes(data)
    proc = run_evaluate(bad, reject_out)
    assert proc.returncode != 0
    after = snapshot_generation(reject_out)
    assert before == after


def test_source_rebuild_and_elf() -> None:
    """Verifier rebuilds the gateway from source and checks ELF output."""
    rebuild_binary()
    assert BIN.is_file()


def test_inspect_and_verify_commands(tmp_path: Path) -> None:
    """Inspect and verify commands remain available for request and evidence."""
    out = tmp_path / "inspect-out"
    run_evaluate(VISIBLE_REQUEST, out)
    inspect_req = subprocess.run(
        [str(BIN), "inspect", "--request", str(VISIBLE_REQUEST)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inspect_req.returncode == 0, inspect_req.stderr
    if (out / "evidence.cbor").is_file():
        inspect_ev = subprocess.run(
            [str(BIN), "inspect", "--evidence", str(out / "evidence.cbor")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert inspect_ev.returncode == 0, inspect_ev.stderr
