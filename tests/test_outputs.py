"""Checks for the Dropforge engine reconstruction task.

The agent's /app/engine.js replays each held-out script and must reproduce
the exact final state the true engine produced: the well as a cell-exact
grid of piece ids and the score.
The held-out scripts and their answers live only here, never in the image,
and are disjoint from the shipped recordings.

At authoring time the plausible misreadings of every house convention
(how cells group when they fall after a clear, the three top-edge
behaviors, the wall-rotation kick, and the whole payout - row table,
cascade multiplier, level progression, and empty-well bonus) were swept
as mutant engines, alone and across the full cross product of 24192
readings.
Each misreading the shipped recordings can surface is contradicted by at
least two shipped recordings and at least three held-out games, so the
true reading is pinned by shipped evidence and stays load-bearing here.
The numeric constants are pinned against a range rather than a menu:
every other value breaks at least two shipped recordings.
Any reading the shipped recordings cannot distinguish is contradicted by
zero held-out games, and no held-out game exercises an event class (clear
size, cascade depth, level, empty well) that the shipped set shows fewer
than two times, so the grade never turns on evidence the agent was not
given.
The order in which loose groups settle and whether a row completed
mid-settle is spotted right away are implementer's choices rather than
house conventions, so every game here was checked to play out identically
under every settle order and both timings; any settle loop reproduces
these records.
"""
import functools
import json
import os
import subprocess
import time

REFERENCE_PATH = os.environ.get("REFERENCE_PATH", "/tests/reference.jsonl")
PROGRAM_PATH = os.environ.get("PROGRAM_PATH", "/app/engine.js")
WORK_DIR = os.environ.get("WORK_DIR", "/tmp/dropforge_heldout")

TIME_BUDGET_SEC = 60.0


def _load_reference():
    rows = []
    with open(REFERENCE_PATH) as fh:
        for line in fh:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


@functools.lru_cache(maxsize=1)
def _run():
    rows = _load_reference()
    os.makedirs(WORK_DIR, exist_ok=True)
    outputs = []
    start = time.monotonic()
    for i, r in enumerate(rows):
        path = os.path.join(WORK_DIR, f"g{i:02d}.json")
        with open(path, "w", newline="\n") as fh:
            json.dump({"script": r["script"]}, fh)
        # check=False: a non-zero exit is reported by _results() with the
        # program's stderr attached, which reads better than a traceback.
        proc = subprocess.run(
            ["node", PROGRAM_PATH, path],
            capture_output=True, text=True, timeout=60, check=False,
        )
        outputs.append(proc)
    elapsed = time.monotonic() - start
    return rows, outputs, elapsed


def _results():
    rows, procs, _ = _run()
    out = []
    for r, proc in zip(rows, procs, strict=True):
        assert proc.returncode == 0, (
            f"node exited {proc.returncode}; stderr:\n{proc.stderr[:600]}"
        )
        try:
            got = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            msg = f"output is not JSON: {proc.stdout[:200]!r}"
            raise AssertionError(msg) from exc
        out.append((r["final"], got))
    return out


def test_program_exists():
    """The deliverable /app/engine.js must be present."""
    assert os.path.isfile(PROGRAM_PATH), f"{PROGRAM_PATH} was not created"


def test_wells_cell_exact():
    """The final well grid must match cell for cell, piece id for piece id,
    on every held-out script."""
    bad = [i for i, (ref, got) in enumerate(_results())
           if got.get("well") != ref["well"]]
    assert not bad, f"wells differ on held-out games {bad}"


def test_scores():
    """The final score must match on every held-out script, which is where
    the cascade and multi-row conventions land."""
    bad = [i for i, (ref, got) in enumerate(_results())
           if got.get("score") != ref["score"]]
    assert not bad, f"scores differ on held-out games {bad}"


def test_full_records():
    """The complete final state must be exact on every held-out script."""
    bad = [i for i, (ref, got) in enumerate(_results()) if got != ref]
    assert not bad, f"final states differ on held-out games {bad}"


def test_completes_within_budget():
    """All replays must finish inside the wall-clock ceiling."""
    _, _, elapsed = _run()
    assert elapsed <= TIME_BUDGET_SEC, (
        f"replays took {elapsed:.1f}s, over the {TIME_BUDGET_SEC:.0f}s budget"
    )
