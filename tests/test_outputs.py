"""Grading suite for the path-tile flow settle.

Coverage areas: the settled outcome on the disclosed worked positions, on the
crafted edge positions and across the whole hidden corpus; rejection of the
shortcut readings that follow the active token only, ignore a collision or stop
at the first tile; determinism, and the executed-case floor.
"""
import functools
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _oracle as O

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("AUG_APP", "/app")
BIN = os.environ.get("AUG_BIN", "")
GO = os.environ.get("AUG_GO", "go")
BINNAME = "tsuro"
SEED = 20260727
NGEN = 220

SH = [[7, 2], [6, 3], [0, 5], [1, 4]]

PUBLIC = [
    ({"n": 4, "board": [], "tokens": [{"cell": [1, 1], "p": 7}],
      "active": 0, "tile": SH},
     "TOKENS 1 0:2.1.7"),
    ({"n": 3, "board": [], "tokens": [{"cell": [0, 1], "p": 7}],
      "active": 0, "tile": [[6, 7], [0, 5], [1, 4], [2, 3]]},
     "TOKENS 1 0:out"),
    ({"n": 4, "board": [],
      "tokens": [{"cell": [1, 1], "p": 7}, {"cell": [1, 1], "p": 2}],
      "active": 0, "tile": SH},
     "TOKENS 2 0:out 1:out"),
    ({"n": 5,
      "board": [{"sq": [2, 2], "paths": SH}, {"sq": [3, 2], "paths": SH}],
      "tokens": [{"cell": [1, 2], "p": 7}], "active": 0, "tile": SH},
     "TOKENS 1 0:4.2.7"),
]

EXTRA = [
    {"n": 5, "board": [],
     "tokens": [{"cell": [2, 2], "p": 7}, {"cell": [2, 2], "p": 2},
                {"cell": [2, 2], "p": 0}],
     "active": 0, "tile": [[7, 2], [0, 5], [1, 4], [3, 6]]},
    {"n": 6,
     "board": [{"sq": [c, 3], "paths": SH} for c in range(1, 5)],
     "tokens": [{"cell": [0, 3], "p": 7}], "active": 0, "tile": SH},
    {"n": 4, "board": [],
     "tokens": [{"cell": [2, 1], "p": 7}, {"cell": [2, 1], "p": 2}],
     "active": 1, "tile": SH},
    {"n": 5, "board": [],
     "tokens": [{"cell": [2, 2], "p": 7}, {"cell": [0, 0], "p": 5}],
     "active": 0, "tile": SH},
    {"n": 6,
     "board": [{"sq": [1, 2], "paths": SH}, {"sq": [3, 2], "paths": SH}],
     "tokens": [{"cell": [2, 2], "p": 7}, {"cell": [2, 2], "p": 2}],
     "active": 0, "tile": SH},
]

EXTRA += O.generate(999001, 12, novel=True)

@functools.lru_cache(maxsize=1)
def HIDDEN():
    return O.generate(SEED, NGEN, novel=True)

PUB_INSTS = [p[0] for p in PUBLIC]


@functools.lru_cache(maxsize=1)
def ALL():
    return PUB_INSTS + EXTRA + HIDDEN()


@functools.lru_cache(maxsize=1)
def EXPECT():
    return [O.evaluate(i) for i in ALL()]

_state = {}


def _build_candidate():
    if BIN:
        return BIN
    r = subprocess.run(["make", "build"], cwd=APP, capture_output=True,
                       text=True, timeout=600, check=False)
    assert r.returncode == 0, f"candidate build failed: {r.stderr[-1500:]}"
    b = os.path.join(APP, "bin", BINNAME)
    assert os.path.exists(b)
    return b


def _run(binary, insts, timeout=420):
    d = tempfile.mkdtemp(prefix="tsuro_")
    ip, op = os.path.join(d, "in.jsonl"), os.path.join(d, "out.txt")
    with open(ip, "w") as f:
        f.writelines(json.dumps(it, separators=(",", ":"), sort_keys=True)
                     + "\n" for it in insts)
    try:
        r = subprocess.run([binary, ip, op], capture_output=True,
                           text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise AssertionError(
            f"candidate did not finish in {timeout}s: {e}") from e
    assert r.returncode == 0, f"candidate exited {r.returncode}: {r.stderr[-800:]}"
    with open(op) as f:
        return [ln.rstrip("\n") for ln in f]


def _cached_run(key, binary, insts, timeout=420):
    """Cache every outcome -- success, failure and timeout alike -- so a slow or
    broken candidate is launched once per input set, not once per test."""
    store = _state.setdefault("runs", {})
    if key not in store:
        try:
            store[key] = ("ok", _run(binary, insts, timeout=timeout))
        except AssertionError as e:
            store[key] = ("err", str(e))
    kind, val = store[key]
    if kind == "err":
        raise AssertionError(val)
    return val


def candidate_outputs():
    return _cached_run("all", _build_candidate(), ALL())


def _build_wrong(name):
    src = os.path.join(HERE, name + ".go")
    d = tempfile.mkdtemp(prefix="wrong_")
    with open(os.path.join(d, "main.go"), "w") as f, open(src) as sf:
        f.write(sf.read())
    with open(os.path.join(d, "go.mod"), "w") as f:
        f.write("module tsuro\n\ngo 1.24\n")
    b = os.path.join(d, BINNAME)
    r = subprocess.run(
        [GO, "build", "-o", b, "."], cwd=d,
        capture_output=True, text=True, timeout=600, check=False)
    assert r.returncode == 0, f"wrong build failed: {r.stderr[-800:]}"
    return b


@pytest.mark.parametrize("inst,want", PUBLIC)
def test_public_example(inst, want):
    """Public position settles to its stated surviving and eliminated tokens."""
    assert O.evaluate(inst) == want
    out = candidate_outputs()
    assert out[ALL().index(inst)] == want


@pytest.mark.parametrize("i", range(len(EXTRA)))
def test_extra_edge_matches_oracle(i):
    """Each crafted edge position matches the independent settlement oracle."""
    out = candidate_outputs()
    idx = len(PUB_INSTS) + i
    assert out[idx] == EXPECT()[idx], (ALL()[idx], out[idx], EXPECT()[idx])


@pytest.mark.parametrize("i", range(NGEN))
def test_hidden_instance_matches_oracle(i):
    """Each generated position matches the oracle survivor set and facings."""
    out = candidate_outputs()
    idx = len(PUB_INSTS) + len(EXTRA) + i
    assert out[idx] == EXPECT()[idx], (ALL()[idx], out[idx], EXPECT()[idx])


def test_rotation_metamorphic():
    """A 180-degree board rotation maps every token position and verdict."""
    b = _build_candidate()
    subset = HIDDEN()[:80]
    rots = [O.rotate180_instance(i) for i in subset]
    base = _run(b, subset)
    rotd = _run(b, rots)
    for i in range(len(subset)):
        assert O.rotate180_output(base[i], subset[i]["n"]) == rotd[i], (
            subset[i], base[i], rotd[i])


def test_candidate_equals_oracle_everywhere():
    """Candidate output equals the oracle on every committed and hidden fixture."""
    out = candidate_outputs()
    assert len(out) == len(ALL())
    for i in range(len(ALL())):
        assert out[i] == EXPECT()[i], (ALL()[i], out[i], EXPECT()[i])


WRONGS = ["wrong_active_only", "wrong_stop_first_tile", "wrong_no_collision"]


@pytest.mark.parametrize("name", WRONGS)
def test_wrong_baseline_rejected(name):
    """Each planted wrong engine disagrees with the oracle on at least one case."""
    b = _build_wrong(name)
    out = _run(b, ALL())
    mism = sum(1 for i in range(len(ALL())) if out[i] != EXPECT()[i])
    assert mism > 0, f"{name} matched the oracle on every position"


def test_determinism_second_run():
    """Reseeded generation and a candidate re-run are byte-identical."""
    assert O.generate(SEED, NGEN, novel=True) == HIDDEN()
    b = _build_candidate()
    assert _run(b, ALL()) == _run(b, ALL())


def test_routes_agree_everywhere():
    """The two independent oracle routes agree on every committed and hidden case."""
    for it in ALL():
        assert O.evaluate_route_a(it) == O.evaluate_route_b(it), O.to_line(it)


def test_no_stored_answer_table_ships_with_the_tests():
    """The tests directory records no settled result for any position. The cache
    directories a run creates are skipped, since they carry no such data."""
    skip = {"__pycache__", ".pytest_cache", ".ruff_cache"}
    names = []
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [x for x in dirs if x not in skip]
        names.extend(f for f in files if not f.endswith(".pyc"))
    allowed = {"_oracle.py", "test.sh", "test_outputs.py"}
    allowed |= {w + ".go" for w in WRONGS}
    assert set(names) == allowed, sorted(names)


def test_case_floor():
    """The executed semantic-case inventory stays at or above the floor of 60."""
    total = len(PUBLIC) + len(EXTRA) + len(HIDDEN()) + len(WRONGS)
    assert total >= 60, total
