import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
STATE = APP / "state" / "trusted.sth"
BIN = APP / "ctcheck"
CARGO = Path("/usr/local/cargo/bin/cargo")
LOG_ID = b"log-alpha"
PUBLIC_KEY = b"monitor-key-01"


def h(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def hx(data: bytes) -> str:
    return data.hex()


def leaf_hash(payload: bytes) -> bytes:
    return h(b"\x00" + payload)


def node_hash(left: bytes, right: bytes) -> bytes:
    return h(b"\x01" + left + right)


def split_point(n: int) -> int:
    k = 1
    while (k << 1) < n:
        k <<= 1
    return k


def tree_hash(leaves: list[bytes]) -> bytes:
    if not leaves:
        return h(b"")
    if len(leaves) == 1:
        return leaf_hash(leaves[0])
    k = split_point(len(leaves))
    return node_hash(tree_hash(leaves[:k]), tree_hash(leaves[k:]))


def consistency_proof(old_size: int, leaves: list[bytes]) -> list[bytes]:
    def walk(old_n: int, sub: list[bytes]) -> list[bytes]:
        new_n = len(sub)
        if old_n == 0 or old_n == new_n:
            return []
        k = split_point(new_n)
        if old_n <= k:
            return [tree_hash(sub[k:])] + walk(old_n, sub[:k])
        return [tree_hash(sub[:k])] + walk(old_n - k, sub[k:])

    return walk(old_size, leaves)


def signature(size: int, root_hex: str, log_id: bytes = LOG_ID) -> str:
    transcript = (
        b"CTSTH\0"
        + log_id
        + b"\0"
        + str(size).encode()
        + b"\0"
        + root_hex.encode()
        + b"\0"
    )
    return h(PUBLIC_KEY + transcript).hex()


def write_case(
    path: Path,
    old_size: int,
    leaves: list[bytes],
    *,
    proof_override=None,
    old_sig_override=None,
    sig_override=None,
    log_id: bytes = LOG_ID,
) -> tuple[str, str]:
    old_root = tree_hash(leaves[:old_size]).hex()
    new_root = tree_hash(leaves).hex()
    proof = consistency_proof(old_size, leaves) if proof_override is None else proof_override
    old_sig = signature(old_size, old_root, log_id) if old_sig_override is None else old_sig_override
    new_sig = signature(len(leaves), new_root, log_id) if sig_override is None else sig_override
    path.write_text(
        "\n".join(
            [
                f"log_id={log_id.hex()}",
                f"public_key={PUBLIC_KEY.hex()}",
                f"old_size={old_size}",
                f"old_root={old_root}",
                f"old_sig={old_sig}",
                f"new_size={len(leaves)}",
                f"new_root={new_root}",
                f"new_sig={new_sig}",
                "entries=" + ",".join(x.hex() for x in leaves),
                "proof=" + ",".join(x.hex() for x in proof),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return old_root, new_root


def run_case(case_path: Path) -> tuple[dict, str]:
    subprocess.run([str(CARGO), "build", "--release"], cwd=APP, check=True, timeout=120)
    assert BIN.exists(), "/app/ctcheck must be the executable command path"
    proc = subprocess.run(
        [str(BIN), str(case_path)],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), STATE.read_text(encoding="utf-8")


def run_raw(*args: str) -> subprocess.CompletedProcess[str]:
    subprocess.run([str(CARGO), "build", "--release"], cwd=APP, check=True, timeout=120)
    assert BIN.exists(), "/app/ctcheck must be the executable command path"
    return subprocess.run(
        [str(BIN), *args],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def run_case_with_trace(case_path: Path, trace_path: Path) -> tuple[dict, str, str]:
    subprocess.run([str(CARGO), "build", "--release"], cwd=APP, check=True, timeout=120)
    assert BIN.exists(), "/app/ctcheck must be the executable command path"
    proc = subprocess.run(
        [
            "strace",
            "-s",
            "4096",
            "-yy",
            "-e",
            "trace=open,openat,write,fsync,fdatasync,rename,renameat,renameat2,close",
            "-o",
            str(trace_path),
            str(BIN),
            str(case_path),
        ],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), STATE.read_text(encoding="utf-8"), trace_path.read_text(encoding="utf-8")


def set_state(size: int, root: str) -> str:
    state = f"{LOG_ID.hex()} {size} {root}\n"
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(state, encoding="utf-8")
    return state


def test_accepts_authenticated_append_only_checkpoint(tmp_path):
    """A valid signed checkpoint, RFC6962 tree root, and consistency proof advance trusted state."""
    leaves = [b"cert-A", b"cert-B", b"cert-C", b"cert-D", b"cert-E"]
    case = tmp_path / "valid.case"
    old_root, new_root = write_case(case, 2, leaves)
    set_state(2, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "ACCEPT", "tree_size": 5, "root_hash": new_root}
    assert state_after == f"{LOG_ID.hex()} 5 {new_root}\n"


def test_updates_state_by_exact_replacement_without_temp_residue(tmp_path):
    """Accepted dossiers write, sync, and rename a temporary state file in order."""
    leaves = [b"durable-A", b"durable-B", b"durable-C"]
    case = tmp_path / "durable.case"
    old_root, new_root = write_case(case, 1, leaves)
    set_state(1, old_root)
    trace = tmp_path / "ctcheck.strace"

    verdict, state_after, trace_text = run_case_with_trace(case, trace)

    assert verdict == {"status": "ACCEPT", "tree_size": 3, "root_hash": new_root}
    expected_state = f"{LOG_ID.hex()} 3 {new_root}\n"
    assert state_after == expected_state
    assert STATE.read_bytes() == expected_state.encode()
    assert not list(STATE.parent.glob("trusted.sth.tmp*"))

    trace_lines = trace_text.splitlines()
    rename_index = next(
        i for i, line in enumerate(trace_lines) if "rename" in line and '"/app/state/trusted.sth"' in line and "= 0" in line
    )
    rename_line = trace_lines[rename_index]
    temp_match = re.search(r'"(/app/state/[^"]+)".*"/app/state/trusted\.sth"', rename_line)
    assert temp_match, rename_line
    temp_path = temp_match.group(1)
    assert temp_path != "/app/state/trusted.sth"

    temp_open = next(
        (line for line in trace_lines[:rename_index] if ("open(" in line or "openat(" in line) and f'"{temp_path}"' in line and "= " in line),
        None,
    )
    assert temp_open is not None, trace_text
    fd_match = re.search(r"= (\d+)(?:<|$)", temp_open)
    assert fd_match, temp_open
    temp_fd = fd_match.group(1)
    write_index = next(
        (i for i, line in enumerate(trace_lines[:rename_index]) if re.search(rf"write\({temp_fd}(?:<|,)", line)),
        None,
    )
    sync_index = next(
        (i for i, line in enumerate(trace_lines[:rename_index]) if re.search(rf"f?datasync\({temp_fd}(?:<|\))", line) or re.search(rf"fsync\({temp_fd}(?:<|\))", line)),
        None,
    )
    assert write_index is not None, trace_text
    assert sync_index is not None, trace_text
    assert write_index < sync_index < rename_index
    assert re.search(rf"write\({temp_fd}(?:<|,).*{re.escape(expected_state.rstrip())}", trace_lines[write_index]), trace_text

    state_write_flags = re.compile(r'"/app/state/trusted\.sth"[^\n]*(O_WRONLY|O_RDWR|O_CREAT|O_TRUNC)')
    assert not any(state_write_flags.search(line) for line in trace_lines[:rename_index]), trace_text
    assert not any(re.search(rf"write\({temp_fd}(?:<|,).*{re.escape(expected_state)}", line) for line in trace_lines[rename_index + 1 :]), trace_text

    dir_fds = set()
    for line in trace_lines:
        if ("open(" in line or "openat(" in line) and '"/app/state"' in line and "= " in line:
            dir_fd_match = re.search(r"= (\d+)(?:<|$)", line)
            assert dir_fd_match, line
            dir_fds.add(dir_fd_match.group(1))
    assert dir_fds, trace_text
    assert any(
        (
            re.search(r"f?datasync\(\d+</app/state(?:/)?>(?:,|\))", line)
            or re.search(r"fsync\(\d+</app/state(?:/)?>(?:,|\))", line)
            or any(
                re.search(rf"f?datasync\({dir_fd}(?:<|\))", line)
                or re.search(rf"fsync\({dir_fd}(?:<|\))", line)
                for dir_fd in dir_fds
            )
        )
        for line in trace_lines[rename_index + 1 :]
    ), trace_text


def test_accepts_empty_previous_tree_with_no_proof(tmp_path):
    """When old_size is zero, no proof entries are permitted and a valid append is accepted."""
    leaves = [b"first", b"second"]
    case = tmp_path / "zero-old.case"
    old_root, new_root = write_case(case, 0, leaves)
    set_state(0, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "ACCEPT", "tree_size": 2, "root_hash": new_root}
    assert state_after == f"{LOG_ID.hex()} 2 {new_root}\n"


def test_accepts_equal_size_checkpoint_with_no_proof(tmp_path):
    """When old_size equals new_size, an authenticated same-tree checkpoint needs no proof."""
    leaves = [b"stable-A", b"stable-B", b"stable-C", b"stable-D"]
    case = tmp_path / "equal-size.case"
    old_root, new_root = write_case(case, 4, leaves)
    before = set_state(4, old_root)

    verdict, state_after = run_case(case)

    assert new_root == old_root
    assert verdict == {"status": "ACCEPT", "tree_size": 4, "root_hash": new_root}
    assert state_after == before


@pytest.mark.parametrize("old_size", [0, 3])
def test_rejects_unneeded_proof_entries_without_state_change(tmp_path, old_size):
    """Zero-size and equal-size consistency cases reject dossiers that include proof entries."""
    leaves = [b"proofless-A", b"proofless-B", b"proofless-C"]
    case = tmp_path / f"unexpected-proof-{old_size}.case"
    old_root, _ = write_case(case, old_size, leaves, proof_override=[b"\x99" * 32])
    before = set_state(old_size, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "CONSISTENCY"}
    assert state_after == before


def test_rejects_proof_that_does_not_authenticate_prefix(tmp_path):
    """Roots and signatures are not enough when the consistency proof does not derive the old root."""
    leaves = [b"alpha", b"beta", b"gamma", b"delta", b"epsilon", b"zeta"]
    case = tmp_path / "bad-proof.case"
    wrong_proof = [b"\x42" * 32 for _ in consistency_proof(3, leaves)]
    old_root, _ = write_case(case, 3, leaves, proof_override=wrong_proof)
    before = set_state(3, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "CONSISTENCY"}
    assert state_after == before


def test_rejects_noncanonical_checkpoint_signature_without_state_change(tmp_path):
    """Checkpoint signatures must bind the specified transcript and rejected dossiers cannot rewrite state."""
    leaves = [b"one", b"two", b"three", b"four"]
    case = tmp_path / "bad-sig.case"
    old_root, _ = write_case(case, 2, leaves, sig_override=h(b"wrong transcript").hex())
    before = set_state(2, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "SIGNATURE"}
    assert state_after == before


def test_rejects_noncanonical_old_checkpoint_signature_without_state_change(tmp_path):
    """The prior checkpoint signature is verified independently of an otherwise valid dossier."""
    leaves = [b"prior-one", b"prior-two", b"prior-three", b"prior-four", b"prior-five"]
    case = tmp_path / "bad-old-sig.case"
    old_root, _ = write_case(case, 3, leaves, old_sig_override=h(b"wrong old transcript").hex())
    before = set_state(3, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "SIGNATURE"}
    assert state_after == before


def test_rejects_tree_root_without_leaf_and_node_domain_separation(tmp_path):
    """The new root must use separate RFC6962 leaf and node hash domains."""
    leaves = [b"same", b"prefix", b"history"]
    old_root = tree_hash(leaves[:1]).hex()
    bad_root = hashlib.sha256(
        hashlib.sha256(leaves[0]).digest()
        + hashlib.sha256(leaves[1]).digest()
        + hashlib.sha256(leaves[2]).digest()
    ).hexdigest()
    case = tmp_path / "bad-root.case"
    write_case(case, 1, leaves)
    text = case.read_text(encoding="utf-8")
    good_new = tree_hash(leaves).hex()
    text = text.replace(f"new_root={good_new}", f"new_root={bad_root}")
    text = text.replace(
        f"new_sig={signature(len(leaves), good_new)}",
        f"new_sig={signature(len(leaves), bad_root)}",
    )
    case.write_text(text, encoding="utf-8")
    before = set_state(1, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "ROOT"}
    assert state_after == before


def test_rejects_bad_root_before_tree_size_regression_without_state_change(tmp_path):
    """A dossier with both a bad new root and a smaller new size reports the documented ROOT priority."""
    old_entries = [b"root-first-A", b"root-first-B", b"root-first-C"]
    new_entries = [b"root-first-A", b"root-first-B"]
    old_root = tree_hash(old_entries).hex()
    good_new_root = tree_hash(new_entries).hex()
    bad_new_root = "77" * 32
    assert bad_new_root != good_new_root
    case = tmp_path / "root-before-regression.case"
    case.write_text(
        "\n".join(
            [
                f"log_id={LOG_ID.hex()}",
                f"public_key={PUBLIC_KEY.hex()}",
                "old_size=3",
                f"old_root={old_root}",
                f"old_sig={signature(3, old_root)}",
                "new_size=2",
                f"new_root={bad_new_root}",
                f"new_sig={signature(2, bad_new_root)}",
                "entries=" + ",".join(x.hex() for x in new_entries),
                "proof=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    before = set_state(3, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "ROOT"}
    assert state_after == before


def test_rejects_authenticated_tree_size_regression_without_state_change(tmp_path):
    """A signed dossier with a smaller new tree is a consistency failure and preserves state."""
    old_entries = [b"regress-A", b"regress-B", b"regress-C", b"regress-D", b"regress-E"]
    new_entries = [b"regress-A", b"regress-B", b"regress-C"]
    old_root = tree_hash(old_entries).hex()
    new_root = tree_hash(new_entries).hex()
    case = tmp_path / "size-regression.case"
    case.write_text(
        "\n".join(
            [
                f"log_id={LOG_ID.hex()}",
                f"public_key={PUBLIC_KEY.hex()}",
                "old_size=5",
                f"old_root={old_root}",
                f"old_sig={signature(5, old_root)}",
                "new_size=3",
                f"new_root={new_root}",
                f"new_sig={signature(3, new_root)}",
                "entries=" + ",".join(x.hex() for x in new_entries),
                "proof=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    before = set_state(5, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "CONSISTENCY"}
    assert state_after == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text: text + "old_size=2\n",
        lambda text: "\n".join(
            line for line in text.splitlines() if not line.startswith("new_sig=")
        )
        + "\n",
        lambda text: text.replace(f"log_id={LOG_ID.hex()}", "log_id=6c6f672d616c7068610"),
        lambda text: text.replace("entries=", "entries=zz,"),
    ],
)
def test_rejects_malformed_dossiers_without_state_change(tmp_path, mutate):
    """Malformed duplicate, missing, and non-hex fields are rejected before state changes."""
    leaves = [b"red", b"green", b"blue"]
    case = tmp_path / "malformed.case"
    old_root, _ = write_case(case, 1, leaves)
    case.write_text(mutate(case.read_text(encoding="utf-8")), encoding="utf-8")
    before = set_state(1, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "MALFORMED"}
    assert state_after == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text, good_new: text.replace(f"old_root={tree_hash([b'red']).hex()}", f"old_root={'00' * 31}"),
        lambda text, good_new: text.replace(f"new_root={good_new}", f"new_root={'11' * 33}"),
        lambda text, good_new: text.replace(f"old_sig={signature(1, tree_hash([b'red']).hex())}", f"old_sig={'22' * 31}"),
        lambda text, good_new: text.replace(f"new_sig={signature(3, good_new)}", f"new_sig={'33' * 33}"),
        lambda text, good_new: text.replace("proof=", f"proof={'44' * 31},"),
        lambda text, good_new: text.replace(f"log_id={LOG_ID.hex()}", f"log_id={'55' * 8}"),
        lambda text, good_new: text.replace(f"public_key={PUBLIC_KEY.hex()}", f"public_key={'66' * 15}"),
    ],
)
def test_rejects_malformed_cryptographic_lengths_without_state_change(tmp_path, mutate):
    """Cryptographic identifiers, digests, signatures, and proof entries have exact byte lengths."""
    leaves = [b"red", b"green", b"blue"]
    case = tmp_path / "bad-length.case"
    old_root, good_new = write_case(case, 1, leaves)
    case.write_text(mutate(case.read_text(encoding="utf-8"), good_new), encoding="utf-8")
    before = set_state(1, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "MALFORMED"}
    assert state_after == before


def test_rejects_dossier_for_different_log_without_state_change(tmp_path):
    """A dossier whose log identity differs from the trusted state is rejected without rewriting state."""
    leaves = [b"north", b"south", b"east", b"west"]
    case = tmp_path / "wrong-log.case"
    old_root, _ = write_case(case, 2, leaves, log_id=b"log-bravo")
    before = set_state(2, old_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": "STATE"}
    assert state_after == before


def test_command_line_misuse_exits_nonzero_without_state_change(tmp_path):
    """The command exits nonzero only when invoked with the wrong number of dossier paths."""
    leaves = [b"cli"]
    case = tmp_path / "cli.case"
    old_root, _ = write_case(case, 0, leaves)
    before = set_state(0, old_root)

    no_args = run_raw()
    too_many = run_raw(str(case), str(case))

    assert no_args.returncode != 0
    assert too_many.returncode != 0
    assert STATE.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    ("mutate", "state_size", "expected"),
    [
        (lambda text, good_new: text + "old_size=1\n", 1, "MALFORMED"),
        (lambda text, good_new: text.replace(f"new_sig={signature(4, good_new)}", "new_sig=00"), 0, "MALFORMED"),
        (
            lambda text, good_new: text.replace(f"new_sig={signature(4, good_new)}", "new_sig=00").replace(
                f"new_root={good_new}", f"new_root={'11' * 32}"
            ),
            1,
            "MALFORMED",
        ),
        (
            lambda text, good_new: text.replace(f"new_root={good_new}", f"new_root={'22' * 32}")
            .replace(f"new_sig={signature(4, good_new)}", f"new_sig={signature(4, '22' * 32)}")
            .replace(next(line for line in text.splitlines() if line.startswith("proof=")), f"proof={'33' * 32}"),
            1,
            "ROOT",
        ),
    ],
)
def test_rejection_reason_priority_preserves_state(tmp_path, mutate, state_size, expected):
    """When several validations fail, the documented first applicable rejection reason wins."""
    leaves = [b"priority-A", b"priority-B", b"priority-C", b"priority-D"]
    case = tmp_path / f"priority-{expected}.case"
    old_root, good_new = write_case(case, 1, leaves)
    case.write_text(mutate(case.read_text(encoding="utf-8"), good_new), encoding="utf-8")
    state_root = old_root if state_size == 1 else tree_hash([]).hex()
    before = set_state(state_size, state_root)

    verdict, state_after = run_case(case)

    assert verdict == {"status": "REJECT", "reason": expected}
    assert state_after == before
