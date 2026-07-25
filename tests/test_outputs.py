import glob
import os
import subprocess
from shutil import copyfile
from tempfile import mkdtemp

import pytest

APP_ROOT = "/app"
TESTS_ROOT = "/tests"
RECOVERED_SRC = os.path.join(APP_ROOT, "src", "recovered.c")
MAKE_SRC = os.path.join(APP_ROOT, "Makefile")
REFERENCE_BIN = os.path.join(APP_ROOT, "bin", "timers")
VISIBLE_DIR = os.path.join(APP_ROOT, "inputs")
HIDDEN_DIR = os.path.join(TESTS_ROOT, "inputs_hidden")
GOLDEN_DIR = os.path.join(TESTS_ROOT, "golden")
REFERENCE_DIR = os.path.join(TESTS_ROOT, "reference")
UNPRIVILEGED = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups"]


def _inputs(directory):
    return sorted(glob.glob(os.path.join(directory, "*.bin")))


VISIBLE_INPUTS = _inputs(VISIBLE_DIR)
HIDDEN_INPUTS = _inputs(HIDDEN_DIR)


def _family(name):
    return sorted(glob.glob(os.path.join(HIDDEN_DIR, f"hidden_{name}_*.bin")))


def _ids(paths):
    return [os.path.basename(path) for path in paths]


def _golden(path):
    base = os.path.join(GOLDEN_DIR, os.path.basename(path))
    with open(base + ".out", "rb") as handle:
        payload = handle.read()
    with open(base + ".code") as handle:
        code = int(handle.read())
    return payload, code


def _payload(path):
    with open(path, "rb") as handle:
        return handle.read()


def _share(directory):
    os.chmod(directory, 0o755)
    return directory


def _run(binary, path, cwd):
    done = subprocess.run(
        UNPRIVILEGED + [binary],
        input=_payload(path),
        capture_output=True,
        timeout=300,
        cwd=cwd,
        check=False,
    )
    return done.stdout, done.returncode


def _compile(source, output):
    return subprocess.run(
        ["gcc", "-std=c11", "-O2", "-o", output, source],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="session")
def agent_binary():
    """Compile only the recovered source and the public build rules in isolation."""
    build_dir = _share(mkdtemp(prefix="tw_agent_build_"))
    os.makedirs(os.path.join(build_dir, "src"), exist_ok=True)
    _share(os.path.join(build_dir, "src"))
    copyfile(RECOVERED_SRC, os.path.join(build_dir, "src", "recovered.c"))
    copyfile(MAKE_SRC, os.path.join(build_dir, "Makefile"))
    result = subprocess.run(
        ["make", "recovered"],
        cwd=build_dir,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = os.path.join(build_dir, "build", "recovered")
    assert os.path.exists(output)
    _share(os.path.join(build_dir, "build"))
    os.chmod(output, 0o755)
    if os.path.exists(REFERENCE_BIN):
        os.remove(REFERENCE_BIN)
    yield output, _share(mkdtemp(prefix="tw_agent_run_"))


def _baseline(source_name):
    build_dir = _share(mkdtemp(prefix="tw_wrong_build_"))
    output = os.path.join(build_dir, source_name.removesuffix(".c"))
    result = _compile(os.path.join(REFERENCE_DIR, source_name), output)
    assert result.returncode == 0, result.stdout + result.stderr
    os.chmod(output, 0o755)
    return output


@pytest.fixture(scope="session")
def wrong_unsigned():
    """A recovery whose due test compares the deadline and the clock as unsigned."""
    return _baseline("wrong_unsigned.c")


@pytest.fixture(scope="session")
def wrong_boundary():
    """A recovery that admits the exact boundary delta into the nearer tier."""
    return _baseline("wrong_boundary.c")


@pytest.fixture(scope="session")
def wrong_append():
    """A recovery that keeps every pending group in arrival order."""
    return _baseline("wrong_append.c")


@pytest.fixture(scope="session")
def wrong_cascade():
    """A recovery that re-homes a due group in list order instead of reversing it."""
    return _baseline("wrong_cascade.c")


@pytest.fixture(scope="session")
def wrong_delegate():
    """A recovery that execs the reference artifact instead of reproducing it."""
    return _baseline("wrong_delegate.c")


@pytest.fixture(scope="session")
def wrong_rearm():
    """A recovery that treats a cancelled id as armable again straight away."""
    return _baseline("wrong_rearm.c")


@pytest.fixture(scope="session")
def visible_lookup():
    """An overfit answer map that recognizes only the public example traces."""
    return _baseline("hardcoded_visible.c")


def _assert_match(agent_binary, path):
    binary, cwd = agent_binary
    stdout, code = _run(binary, path, cwd)
    want, want_code = _golden(path)
    assert stdout == want
    assert code == want_code


def _moved(wrong, paths):
    total = 0
    for path in paths:
        if _run(wrong, path, None) != _golden(path):
            total += 1
    return total


def test_executed_case_floor_and_golden_coverage():
    """The hidden battery holds at least 120 distinct traces with complete goldens."""
    assert len(HIDDEN_INPUTS) >= 120
    hidden_bytes = {_payload(path) for path in HIDDEN_INPUTS}
    visible_bytes = {_payload(path) for path in VISIBLE_INPUTS}
    assert len(hidden_bytes) == len(HIDDEN_INPUTS)
    assert not (hidden_bytes & visible_bytes)
    for path in VISIBLE_INPUTS + HIDDEN_INPUTS:
        base = os.path.join(GOLDEN_DIR, os.path.basename(path))
        assert os.path.exists(base + ".out")
        assert os.path.exists(base + ".code")


def test_every_error_token_is_exercised():
    """The battery reaches all five disclosed error tokens."""
    seen = set()
    for path in HIDDEN_INPUTS:
        payload, code = _golden(path)
        if code == 1:
            seen.add(payload.strip().split(b"\n")[-1])
    assert seen == {
        b"ERR syntax",
        b"ERR range",
        b"ERR ops",
        b"ERR capacity",
        b"ERR budget",
    }


@pytest.mark.parametrize("path", VISIBLE_INPUTS, ids=_ids(VISIBLE_INPUTS))
def test_recovered_matches_visible_traces(agent_binary, path):
    """The recovered source matches every public example byte for byte."""
    _assert_match(agent_binary, path)


@pytest.mark.parametrize("path", HIDDEN_INPUTS, ids=_ids(HIDDEN_INPUTS))
def test_recovered_matches_hidden_traces(agent_binary, path):
    """The recovered source matches independent goldens on unseen traces."""
    _assert_match(agent_binary, path)


def test_output_envelope_holds_on_every_hidden_trace(agent_binary):
    """Successful runs close with a digest line and failures with one error line."""
    binary, cwd = agent_binary
    for path in HIDDEN_INPUTS:
        stdout, code = _run(binary, path, cwd)
        lines = stdout.decode("ascii").splitlines()
        assert lines
        if code == 0:
            assert lines[-1].startswith("D ")
            assert len(lines[-1]) == 10
        else:
            assert code == 1
            assert lines[-1].startswith("ERR ")


def test_goldens_are_sealed_from_the_graded_uid():
    """The uid that runs the candidate cannot read the goldens it is scored against."""
    target = os.path.join(GOLDEN_DIR, os.path.basename(HIDDEN_INPUTS[0]) + ".out")
    assert os.path.exists(target)
    probe = subprocess.run(
        UNPRIVILEGED + ["cat", target],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert probe.returncode != 0
    assert probe.stdout == b""


def test_reference_is_absent_and_execution_repeats(agent_binary):
    """Grading holds no reference artifact and the candidate repeats exactly."""
    binary, cwd = agent_binary
    assert not os.path.exists(REFERENCE_BIN)
    target = _family("mixed")[0]
    first = _run(binary, target, cwd)
    second = _run(binary, target, cwd)
    assert first == second == _golden(target)


@pytest.mark.parametrize("path", _family("wrap"), ids=_ids(_family("wrap")))
def test_wrap_safe_due_test_is_necessary(agent_binary, path):
    """Traces that carry the clock across its wrap are matched exactly."""
    _assert_match(agent_binary, path)


def test_unsigned_due_test_diverges_across_the_wrap(wrong_unsigned):
    """Comparing deadline and clock as unsigned moves most wrap traces."""
    assert _moved(wrong_unsigned, _family("wrap")) >= 12


@pytest.mark.parametrize("path", _family("bound"), ids=_ids(_family("bound")))
def test_tier_boundary_is_necessary(agent_binary, path):
    """Traces sitting on the exact boundary delta are matched exactly."""
    _assert_match(agent_binary, path)


@pytest.mark.parametrize("path", _family("rearm"), ids=_ids(_family("rearm")))
def test_arming_after_a_cancel_is_necessary(agent_binary, path):
    """The recovered source matches every trace that cancels and arms one id."""
    _assert_match(agent_binary, path)


def test_treating_a_cancelled_id_as_free_diverges(wrong_rearm):
    """Arming a cancelled id straight away diverges on the cancel traces."""
    assert _moved(wrong_rearm, _family("rearm")) >= 8


def test_the_cancel_rule_clears_every_public_trace(wrong_rearm):
    """That same reading matches every shipped example, so samples cannot show it."""
    assert _moved(wrong_rearm, VISIBLE_INPUTS) == 0


def test_boundary_admission_diverges_on_exact_deltas(wrong_boundary):
    """Admitting the boundary delta into the nearer tier moves most boundary traces."""
    assert _moved(wrong_boundary, _family("bound")) >= 10


@pytest.mark.parametrize(
    "path",
    _family("orderdirect") + _family("ordermixed"),
    ids=_ids(_family("orderdirect") + _family("ordermixed")),
)
def test_pending_group_order_is_necessary(agent_binary, path):
    """Traces whose groups come due together are matched in the reference order."""
    _assert_match(agent_binary, path)


def test_arrival_order_recovery_diverges(wrong_append):
    """Keeping groups in arrival order moves the direct and mixed families."""
    assert _moved(wrong_append, _family("orderdirect") + _family("ordermixed")) >= 12


@pytest.mark.parametrize(
    "path",
    _family("ordercascade") + _family("ordermixed"),
    ids=_ids(_family("ordercascade") + _family("ordermixed")),
)
def test_rehomed_group_order_is_necessary(agent_binary, path):
    """Traces whose groups are re-homed before coming due keep the reference order."""
    _assert_match(agent_binary, path)


def test_rehome_order_recovery_diverges(wrong_cascade):
    """Re-homing in list order moves the re-homed and mixed families."""
    assert _moved(wrong_cascade, _family("ordercascade") + _family("ordermixed")) >= 12


def test_shift_pairs_agree_on_the_due_sequence(agent_binary):
    """A trace and its clock-shifted twin report the same ids in the same order."""
    binary, cwd = agent_binary
    bases = sorted(glob.glob(os.path.join(HIDDEN_DIR, "hidden_shift_*a.bin")))
    assert len(bases) >= 4
    for base in bases:
        twin = base[:-5] + "b.bin"
        assert os.path.exists(twin)
        left = _run(binary, base, cwd)[0].decode("ascii").splitlines()
        right = _run(binary, twin, cwd)[0].decode("ascii").splitlines()
        left_ids = [line.split()[2:] for line in left if line.startswith("F ")]
        right_ids = [line.split()[2:] for line in right if line.startswith("F ")]
        assert left_ids == right_ids
        assert any(left_ids)


def test_delegation_wrapper_produces_nothing(agent_binary, wrong_delegate):
    """A recovery that execs the reference fails once the artifact is gone."""
    assert not os.path.exists(REFERENCE_BIN)
    targets = _family("short")
    assert _moved(wrong_delegate, targets) == len(targets)
    for path in targets:
        _assert_match(agent_binary, path)


def test_visible_answer_map_does_not_generalize(visible_lookup):
    """A map over the public traces passes them and fails the hidden battery."""
    for path in VISIBLE_INPUTS:
        assert _run(visible_lookup, path, None) == _golden(path)
    assert _moved(visible_lookup, HIDDEN_INPUTS) == len(HIDDEN_INPUTS)
