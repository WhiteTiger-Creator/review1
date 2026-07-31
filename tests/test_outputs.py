"""Verifier for the Gauntlet champion-selection task.

The submission implements chooseChampion(round) in /app/strategy.js. For each held-out round a
verifier-owned runner records which contender it sends in, and this verifier scores that contender
with an independent Python model of the Warden's hidden bout rule. A round counts when the chosen contender wins as many
bouts as the best contender in that roster could. The checks are banded: one confirms every round
was answered, and the rest require the strategy to settle progressively more of the thirty rounds,
so a strategy that has only part of the rule clears the lower bands and stops there.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
APP = Path(os.environ.get("GAUNTLET_APP_DIR", "/app")).resolve()
RUNNER = TESTS_DIR / "run_strategy.js"
ROUNDS = json.loads((TESTS_DIR / "held_rounds.json").read_text(encoding="utf-8"))["rounds"]

COUNTER_MARGIN = 3

# The strategy runs in a separate, unprivileged process that cannot read this directory: it is
# handed its own copy of the rounds in a scratch directory. Scoring happens back in this process.
NOBODY_UID = 65534
NOBODY_GID = 65534


def _score(u):
    return 2 * u["power"] + u["guile"] - u["armour"]


def _counters(a, b):
    return a["guile"] >= b["armour"] + COUNTER_MARGIN


def _beats(a, b):
    ca, cb = _counters(a, b), _counters(b, a)
    if ca and not cb:
        return True
    if cb and not ca:
        return False
    if _score(a) != _score(b):
        return _score(a) > _score(b)
    if a["power"] != b["power"]:
        return a["power"] > b["power"]
    if a["guile"] != b["guile"]:
        return a["guile"] > b["guile"]
    if a["armour"] != b["armour"]:
        return a["armour"] < b["armour"]
    return True


def _wins(mine, rivals):
    return sum(1 for r in rivals if _beats(mine, r))


def _can_drop_privileges():
    """True when this process is root on a POSIX host and can hand work to another account."""
    return os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0


def _run_isolated(cmd, work):
    """Run the submitted strategy with as little reach into this directory as the host allows."""
    saved = []
    for d in (TESTS_DIR, Path("/solution"), Path("/oracle")):
        try:
            if d.is_dir():
                saved.append((d, d.stat().st_mode & 0o7777))
                d.chmod(0o000)
        except OSError:
            pass
    kwargs = {"capture_output": True, "text": True, "cwd": str(work)}
    if _can_drop_privileges():
        kwargs.update(user=NOBODY_UID, group=NOBODY_GID, env={**os.environ, "HOME": str(work)})
    try:
        try:
            return subprocess.run(cmd, check=False, **kwargs)
        except OSError:
            for key in ("user", "group", "env"):
                kwargs.pop(key, None)
            return subprocess.run(cmd, check=False, **kwargs)
    finally:
        for d, mode in saved:
            try:
                d.chmod(mode)
            except OSError:
                pass


@pytest.fixture(scope="module")
def produced():
    """Run the submitted strategy in a process isolated from the verifier's directory."""
    runner, rounds = RUNNER, TESTS_DIR / "held_rounds.json"
    try:
        work = Path(tempfile.mkdtemp())
        shutil.copy2(RUNNER, work / "run_strategy.js")
        shutil.copy2(rounds, work / "rounds.json")
        runner, rounds = work / "run_strategy.js", work / "rounds.json"
        if _can_drop_privileges():
            work.chmod(0o777)
            for f in (runner, rounds):
                f.chmod(0o644)
            # Whoever runs the strategy still needs to load the submitted module.
            subprocess.run(["chmod", "-R", "a+rX", str(APP)], capture_output=True, check=False)
    except OSError:
        work = Path(tempfile.gettempdir())
    out = work / "picks.json"

    res = _run_isolated(["node", str(runner), str(APP), str(rounds), str(out)], work)
    if res.returncode != 0 or not out.exists():
        raise RuntimeError("run_strategy.js failed: " + (res.stderr or res.stdout))
    return json.loads(out.read_text(encoding="utf-8"))["picks"]


def _rounds_optimal(picks):
    """How many held-out rounds the submitted strategy chose a best champion for."""
    good = 0
    for r in ROUNDS:
        mine, rivals = r["mine"], r["rivals"]
        pick = picks.get(r["name"])
        if not isinstance(pick, int) or not 0 <= pick < len(mine):
            continue
        if _wins(mine[pick], rivals) == max(_wins(m, rivals) for m in mine):
            good += 1
    return good


def test_every_round_answered(produced):
    """The strategy must return a valid champion index for every held-out round."""
    bad = [r["name"] for r in ROUNDS
           if not (isinstance(produced.get(r["name"]), int)
                   and 0 <= produced[r["name"]] < len(r["mine"]))]
    assert not bad, f"no valid champion index for: {bad[:6]}"


def test_beats_a_plain_strength_ranking(produced):
    """Ranking the contenders by raw strength settles 15 of the 30 rounds; beat that clearly."""
    got = _rounds_optimal(produced)
    assert got >= 18, f"chose a best champion on only {got} of {len(ROUNDS)} rounds"


def test_most_rounds_settled(produced):
    """A strategy that has found most of the Warden's rule settles the large majority."""
    got = _rounds_optimal(produced)
    assert got >= 21, f"chose a best champion on only {got} of {len(ROUNDS)} rounds"


def test_rule_recovered(produced):
    """Only a strategy that has found the Warden's overriding condition settles this many."""
    got = _rounds_optimal(produced)
    assert got >= 24, f"chose a best champion on only {got} of {len(ROUNDS)} rounds"
