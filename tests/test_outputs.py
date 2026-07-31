"""Behavioral verifier for the stateful Lock Vault custody engine."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.serialization import load_der_private_key
from reference_model import (
    STAMP_LABEL,
    bag_id,
    encrypt_pbes1_legacy,
    encrypt_rsa,
    encrypt_same_key_pair,
    expected_outputs,
    spki_fingerprint,
    write_vault,
)

APP = Path("/app")
VAULT = APP / "lock_vault"
POLICY = VAULT / "custody_policy.yaml"
BIN = APP / "bin" / "lock-release"
PROBE = VAULT / "probe_desk"
MIN_ITERS = 10_000

CORRECT_POLICY = {
    "gate_mesh": "w3np",
    "desk_latch": "k7rd",
    "iters_floor": "p1yc",
    "floor_companion": "m5hf",
    "fingerprint": "t8vb",
    "scheme_gate": "c4js",
    "cipher_gate": "g9lm",
    "cipher_companion": "a2zq",
    "bag_burn": "r6ux",
    "burn_companion": "e0ki",
    "key_replay": "y4od",
    "stamp_label": "n7pg",
    "stamp_companion": "b5ta",
    "log_clear": "h2we",
    "format_seq": "v9fc",
    "reject_order": "s3mj",
    "order_companion": "d8xa",
    "quiet_stream": "q1ub",
    "hold_window": "f6zk",
    "hold_companion": "j4rn",
}


def write_policy(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "policy_version: 2\n" + "".join(f"{key}: {value}\n" for key, value in values.items()),
        encoding="utf-8",
    )


@pytest.fixture(scope="session", autouse=True)
def rebuilt_lock_release() -> None:
    """Rebuild graded sources so compile failures remain pytest/CTRF results."""
    if BIN.exists():
        BIN.unlink()
    env = os.environ.copy()
    env["CGO_ENABLED"] = "0"
    result = subprocess.run(
        ["/usr/local/go/bin/go", "build", "-o", str(BIN), "."],
        cwd=APP / "lock_lane",
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0 and BIN.is_file(), (
        "custody authorization rebuild failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    BIN.chmod(0o755)


def run_vault(root: Path, out: Path, policy: Path = POLICY) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        LOCK_VAULT_ROOT=str(root),
        LOCK_LOG_PATH=str(out / "unwrap_log.jsonl"),
        LOCK_STAMP_PATH=str(out.parent / "stamp" / "vault_stamp.txt"),
        LOCK_POLICY=str(policy),
    )
    if not BIN.is_file():
        return subprocess.CompletedProcess([str(BIN)], 127, "", "missing lock-release")
    process = subprocess.Popen(
        [str(BIN)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
        return subprocess.CompletedProcess(process.args, 124, "", "lock-release timeout")
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def outputs(out: Path) -> tuple[str, str]:
    return (
        (out / "unwrap_log.jsonl").read_text(encoding="utf-8"),
        (out.parent / "stamp" / "vault_stamp.txt").read_text(encoding="utf-8"),
    )


def make_case(tmp_path: Path, phrases: list[dict], bags: list[dict], floor: int = MIN_ITERS) -> Path:
    root = tmp_path / "vault"
    write_vault(root, phrases, floor, bags)
    return root


def test_editable_engine_and_unique_policy_layout() -> None:
    """The graded image exposes every custody surface authorized by the instruction."""
    assert (APP / "lock_lane" / "main.go").is_file()
    assert (APP / "lock_lane" / "go.mod").is_file()
    assert POLICY.is_file()


def test_live_sheet_is_complete_and_faithful() -> None:
    """The released policy selects every closed behavior required by the verifier."""
    text = POLICY.read_text(encoding="utf-8")
    for key, value in CORRECT_POLICY.items():
        assert f"{key}: {value}\n" in text


def test_public_doctrine_has_no_hash_token_recipe() -> None:
    """Public authority uses opaque glyphs and never revives Family 23/24 derivation."""
    paths = [
        VAULT / "lock_canon.txt",
        VAULT / "closed_token_binding.md",
        VAULT / "policy_mapping.md",
        VAULT / "policy_schema.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "family 23" not in text
    assert "family 24" not in text
    assert "bind|" not in text
    assert "stage-one" not in text


def test_main_batch_matches_independent_model(tmp_path: Path) -> None:
    """The main release batch matches the independent stateful reference model."""
    result = run_vault(VAULT, tmp_path / "out")
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert outputs(tmp_path / "out") == expected_outputs(VAULT)


def test_probe_batch_matches_sealed_observations(tmp_path: Path) -> None:
    """The immutable probe desk reproduces its expected log and stamp exactly."""
    result = run_vault(PROBE, tmp_path / "out")
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    log, stamp = outputs(tmp_path / "out")
    assert log == (PROBE / "expected" / "unwrap_log.jsonl").read_text(encoding="utf-8")
    assert stamp == (PROBE / "expected" / "vault_stamp.txt").read_text(encoding="utf-8")


def test_iteration_floor_is_inclusive_and_not_soft(tmp_path: Path) -> None:
    """Equality passes while a value below the stated floor is denied before unwrap."""
    at_floor = encrypt_rsa("pw", MIN_ITERS)
    low = encrypt_rsa("pw", MIN_ITERS - 1)
    root = make_case(
        tmp_path,
        [{"slot": "a", "phrase": "pw"}, {"slot": "b", "phrase": "pw"}],
        [{"seq": 1, "slot": "a", "der": at_floor.hex()}, {"seq": 2, "slot": "b", "der": low.hex()}],
    )
    assert run_vault(root, tmp_path / "out").returncode == 0
    rows = [json.loads(line) for line in outputs(tmp_path / "out")[0].splitlines()]
    assert [row["verdict"] for row in rows] == ["ok", "iters"]


def test_pbes2_rejection_precedes_unwrap(tmp_path: Path) -> None:
    """A legacy envelope with a wrong phrase is rejected as pbes2, not unwrap."""
    der = encrypt_pbes1_legacy("right")
    root = make_case(tmp_path, [{"slot": "s", "phrase": "wrong"}], [{"seq": 1, "slot": "s", "der": der.hex()}])
    run_vault(root, tmp_path / "out")
    assert json.loads(outputs(tmp_path / "out")[0])["verdict"] == "pbes2"


def test_cipher_rejection_precedes_unwrap(tmp_path: Path) -> None:
    """A PBES2 AES-128 bag with a wrong phrase is rejected as cipher first."""
    der = encrypt_rsa("right", MIN_ITERS, "aes-128-cbc")
    root = make_case(tmp_path, [{"slot": "s", "phrase": "wrong"}], [{"seq": 1, "slot": "s", "der": der.hex()}])
    run_vault(root, tmp_path / "out")
    assert json.loads(outputs(tmp_path / "out")[0])["verdict"] == "cipher"


def test_failed_unwrap_burns_exact_der(tmp_path: Path) -> None:
    """A passed-floor bag burns before failed unwrap, so identical DER later replays."""
    der = encrypt_rsa("right", MIN_ITERS)
    root = make_case(
        tmp_path,
        [{"slot": "bad", "phrase": "wrong"}, {"slot": "good", "phrase": "right"}],
        [{"seq": 1, "slot": "bad", "der": der.hex()}, {"seq": 2, "slot": "good", "der": der.hex()}],
    )
    run_vault(root, tmp_path / "out")
    assert [json.loads(x)["verdict"] for x in outputs(tmp_path / "out")[0].splitlines()] == ["unwrap", "replay"]


def test_fingerprint_is_spki_not_encrypted_blob(tmp_path: Path) -> None:
    """Accepted fp is the DER SPKI digest and differs from encrypted bag identity."""
    der = encrypt_rsa("pw", MIN_ITERS)
    root = make_case(tmp_path, [{"slot": "s", "phrase": "pw"}], [{"seq": 1, "slot": "s", "der": der.hex()}])
    run_vault(root, tmp_path / "out")
    row = json.loads(outputs(tmp_path / "out")[0])
    key = load_der_private_key(der, password=b"pw")
    assert row["fp"] == spki_fingerprint(key)
    assert row["fp"] != bag_id(der)


def test_distinct_bags_for_same_key_trigger_key_replay(tmp_path: Path) -> None:
    """Different encrypted DER encodings of one public key are caught by SPKI replay."""
    first, second = encrypt_same_key_pair("pw", MIN_ITERS)
    root = make_case(
        tmp_path,
        [{"slot": "s", "phrase": "pw"}],
        [{"seq": 1, "slot": "s", "der": first.hex()}, {"seq": 2, "slot": "s", "der": second.hex()}],
    )
    run_vault(root, tmp_path / "out")
    assert [json.loads(x)["verdict"] for x in outputs(tmp_path / "out")[0].splitlines()] == ["ok", "replay"]


def test_hold_window_is_inclusive_and_does_not_burn(tmp_path: Path) -> None:
    """An accepted hold blocks its slot through the bound without consuming blocked DER."""
    first = encrypt_rsa("pw", MIN_ITERS)
    held = encrypt_rsa("pw", MIN_ITERS)
    root = make_case(
        tmp_path,
        [{"slot": "s", "phrase": "pw"}],
        [
            {"seq": 1, "slot": "s", "der": first.hex(), "hold_until": 3},
            {"seq": 3, "slot": "s", "der": held.hex()},
            {"seq": 4, "slot": "s", "der": held.hex()},
        ],
    )
    run_vault(root, tmp_path / "out")
    assert [json.loads(x)["verdict"] for x in outputs(tmp_path / "out")[0].splitlines()] == ["ok", "hold", "ok"]


def test_stateful_ladder_interactions_share_only_required_state(tmp_path: Path) -> None:
    """One batch composes holds, key replay, failed-unwrap burn, floors, and algorithm precedence."""
    first, same_key = encrypt_same_key_pair("pw", MIN_ITERS)
    failed = encrypt_rsa("right", MIN_ITERS)
    low = encrypt_rsa("pw", MIN_ITERS - 1)
    legacy = encrypt_pbes1_legacy("right")
    root = make_case(
        tmp_path,
        [
            {"slot": "alpha", "phrase": "pw"},
            {"slot": "bad", "phrase": "wrong"},
            {"slot": "good", "phrase": "right"},
            {"slot": "low", "phrase": "pw"},
            {"slot": "legacy", "phrase": "wrong"},
        ],
        [
            {"seq": 1, "slot": "alpha", "der": first.hex(), "hold_until": 3},
            {"seq": 3, "slot": "alpha", "der": same_key.hex()},
            {"seq": 4, "slot": "alpha", "der": same_key.hex()},
            {"seq": 5, "slot": "bad", "der": failed.hex()},
            {"seq": 6, "slot": "good", "der": failed.hex()},
            {"seq": 7, "slot": "low", "der": low.hex()},
            {"seq": 8, "slot": "low", "der": low.hex()},
            {"seq": 9, "slot": "legacy", "der": legacy.hex()},
        ],
    )
    result = run_vault(root, tmp_path / "out")
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert [json.loads(x)["verdict"] for x in outputs(tmp_path / "out")[0].splitlines()] == [
        "ok",
        "hold",
        "replay",
        "unwrap",
        "replay",
        "iters",
        "iters",
        "pbes2",
    ]


def test_companion_flip_demotes_entire_mesh(tmp_path: Path) -> None:
    """Each root or companion flip globally restores noisy, soft-floor, blob-identity behavior."""
    der = encrypt_rsa("pw", MIN_ITERS // 2)
    root = make_case(tmp_path, [{"slot": "s", "phrase": "pw"}], [{"seq": 1, "slot": "s", "der": der.hex()}])
    flips = {
        "gate_mesh": "w3nq",
        "desk_latch": "k7re",
        "floor_companion": "m5hg",
        "cipher_companion": "a2zr",
        "burn_companion": "e0kj",
        "stamp_companion": "b5tb",
        "order_companion": "d8xb",
        "hold_companion": "j4ro",
    }
    for index, (key, value) in enumerate(flips.items()):
        trial = tmp_path / f"trial-{index}.yaml"
        changed = dict(CORRECT_POLICY)
        changed[key] = value
        write_policy(trial, changed)
        out = tmp_path / f"out-{index}"
        result = run_vault(root, out, trial)
        assert result.stdout == "desk\n"
        assert json.loads(outputs(out)[0])["fp"] == bag_id(der)


def test_stamp_binds_label_and_exact_log(tmp_path: Path) -> None:
    """Stamp truncates the labeled digest and not the digest of log bytes alone."""
    der = encrypt_rsa("pw", MIN_ITERS)
    root = make_case(tmp_path, [{"slot": "s", "phrase": "pw"}], [{"seq": 1, "slot": "s", "der": der.hex()}])
    run_vault(root, tmp_path / "out")
    log, stamp = outputs(tmp_path / "out")
    labeled = hashlib.sha256(STAMP_LABEL + log.encode()).hexdigest()[:16]
    bare = hashlib.sha256(log.encode()).hexdigest()[:16]
    assert f"stamp={labeled}\n" in stamp and f"stamp={bare}\n" not in stamp


def test_log_parent_is_recursively_cleared_and_success_quiet(tmp_path: Path) -> None:
    """Successful processing removes stale descendants and emits no diagnostics."""
    der = encrypt_rsa("pw", MIN_ITERS)
    root = make_case(tmp_path, [{"slot": "s", "phrase": "pw"}], [{"seq": 1, "slot": "s", "der": der.hex()}])
    out = tmp_path / "out"
    stale = out / "nested" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    result = run_vault(root, out)
    assert result.stdout == "" and result.stderr == ""
    assert not stale.exists() and (out / "unwrap_log.jsonl").is_file()


def test_inputs_and_authority_files_remain_immutable(tmp_path: Path) -> None:
    """Running the engine does not rewrite evidence, policy inputs, or doctrine."""
    relative_evidence = [
        Path("bags/main/bags.ndjson"),
        Path("phrases/main/phrases.ndjson"),
        Path("policy/iters.json"),
    ]
    copy = tmp_path / "vault"
    shutil.copytree(VAULT, copy)
    before = {path: hashlib.sha256((copy / path).read_bytes()).digest() for path in relative_evidence}
    authority_before = {
        POLICY: hashlib.sha256(POLICY.read_bytes()).digest(),
        VAULT / "lock_canon.txt": hashlib.sha256((VAULT / "lock_canon.txt").read_bytes()).digest(),
    }
    run_vault(copy, tmp_path / "out")
    assert before == {path: hashlib.sha256((copy / path).read_bytes()).digest() for path in relative_evidence}
    assert authority_before == {path: hashlib.sha256(path.read_bytes()).digest() for path in authority_before}
