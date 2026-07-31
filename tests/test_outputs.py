"""Checks the sedgemere level book.

There is no answer key to copy here. The book is handed readings drawn fresh
from the same process the training set came from, on seeds taken from
os.urandom, and is scored on how close its levels come. Nothing memorised from
the shipped files helps, because the readings graded on do not exist until
this file runs.
"""
import math
import os
import random
import subprocess
import time
from pathlib import Path

import pytest

BOOK = os.environ.get("SEDGEMERE_BOOK", "/app/build/sedgemere")
SOURCES = Path(os.environ.get("SEDGEMERE_SOURCES", "/app/src"))
DATA = Path(os.environ.get("SEDGEMERE_DATA", "/app/data"))
TRAIN = DATA / "train.csv"

BAR = 1.35
DRAWS = 3
ROWS_PER_DRAW = 40000
PATIENCE = 300.0
COLUMNS = ["reed", "silt", "brack", "fen", "moss", "gale", "sluice", "weir"]


def _one(rng):
    """One survey of the beck and the level it turned out to hold."""
    reed, silt, brack, fen = (rng.gauss(0, 1) for _ in range(4))
    moss, gale = rng.gauss(0, 1), rng.gauss(0, 1)
    sluice = rng.randint(0, 1)
    weir = rng.randint(0, 1)
    pair = brack * moss if weir else reed * silt
    core = (1.30 * reed - 0.90 * silt + 0.60 * brack
            + 1.40 * pair
            + 2.20 * math.tanh(1.5 * (fen - 0.3))
            + 0.80 * (1 if sluice else -1) * moss)
    spike = rng.random() < 0.17
    slip = math.exp(rng.gauss(1.4, 0.8)) if spike else rng.gauss(0, 0.45)
    return ([reed, silt, brack, fen, moss, gale, sluice, weir], core + slip)


def _draw(n, seed):
    rng = random.Random(seed)
    return [_one(rng) for _ in range(n)]


def _write_readings(path, rows):
    with Path(path).open("w", encoding="ascii") as handle:
        handle.write(",".join(COLUMNS) + "\n")
        handle.writelines(
            ",".join(f"{v:.6f}" if isinstance(v, float) else str(v)
                     for v in xs) + "\n"
            for xs, _level in rows)


def _run_book(rows, tag):
    """Hand the book a fresh draw and read back the levels it gives."""
    work = Path(os.environ.get("SEDGEMERE_WORK", "/tmp")) / f"sedgemere_{tag}"
    work.mkdir(parents=True, exist_ok=True)
    readings = work / "readings.csv"
    levels = work / "levels.txt"
    _write_readings(readings, rows)
    if levels.exists():
        levels.unlink()
    began = time.time()
    trouble = None
    try:
        done = subprocess.run([BOOK, str(readings), str(levels)], check=False,
                              capture_output=True, text=True,
                              timeout=PATIENCE + 60)
        if done.returncode != 0:
            trouble = f"the book exited {done.returncode}: {done.stderr[-800:]}"
    except subprocess.TimeoutExpired:
        trouble = "the book did not finish"
    elapsed = time.time() - began
    said = []
    if levels.exists():
        for raw in levels.read_text().splitlines():
            line = raw.strip()
            if line:
                try:
                    said.append(float(line))
                except ValueError:
                    said.append(None)
    return said, elapsed, trouble


def _miss(said, rows):
    """The average distance between a level given and the level held."""
    return sum(abs(s - level) for s, (_xs, level) in zip(said, rows)) \
        / len(rows)


# Every draw is made here, once, on seeds that did not exist before now.
_SEEDS = [int.from_bytes(os.urandom(4), "big") for _ in range(DRAWS)]
_DRAWN = [_draw(ROWS_PER_DRAW, seed) for seed in _SEEDS]
_RESULTS = [_run_book(rows, f"draw{i}") for i, rows in enumerate(_DRAWN)]


def test_the_book_was_written_and_built():
    """The sources have to be there, and to have been built."""
    assert SOURCES.is_dir(), f"no sources at {SOURCES}"
    assert list(SOURCES.glob("*.cpp")), "no sources to build"
    assert Path(BOOK).is_file(), "nothing was built"


def test_the_book_is_present_and_was_replaced():
    """The book that ships gives every reading the same level. Leaving it as
    it stands is not a solution."""
    text = " ".join(p.read_text() for p in SOURCES.glob("*.cpp"))
    assert "Nothing here learns anything yet" not in text


def test_the_training_data_was_left_alone():
    """The training set is read, never rewritten."""
    rows = [ln for ln in TRAIN.read_text().splitlines() if ln.strip()]
    assert len(rows) == 4001, f"train.csv holds {len(rows) - 1} surveys"


@pytest.mark.parametrize("draw", range(DRAWS))
def test_the_book_answers_in_the_right_shape(draw):
    """One level a line, in the order the readings came, all of them numbers."""
    said, _elapsed, trouble = _RESULTS[draw]
    assert trouble is None, trouble
    assert len(said) == ROWS_PER_DRAW, (
        f"got {len(said)} levels for {ROWS_PER_DRAW} readings")
    assert all(s is not None for s in said), "some levels were not numbers"


@pytest.mark.parametrize("draw", range(DRAWS))
def test_the_book_finishes_inside_the_time_it_is_given(draw):
    _said, elapsed, _trouble = _RESULTS[draw]
    assert elapsed < PATIENCE, (
        f"took {elapsed:.0f}s of the {PATIENCE:.0f}s allowed")


@pytest.mark.parametrize("draw", range(DRAWS))
def test_the_book_clears_the_bar_on_this_fresh_draw(draw):
    """The whole of it: the levels have to come close on readings the book
    has never seen."""
    said, _elapsed, trouble = _RESULTS[draw]
    assert trouble is None, trouble
    got = _miss(said, _DRAWN[draw])
    assert got <= BAR, f"average miss {got:.4f}, and {BAR} is the bar"


def test_the_book_holds_up_across_draws():
    """A book tuned to one particular sample will not do."""
    misses = [_miss(said, _DRAWN[i])
              for i, (said, _e, trouble) in enumerate(_RESULTS)
              if trouble is None and len(said) == ROWS_PER_DRAW]
    assert len(misses) == DRAWS, "some draws were not answered"
    assert sum(misses) / len(misses) <= BAR, (
        f"the average miss across draws was {sum(misses) / len(misses):.4f}")


def test_the_book_beats_reading_the_same_level_every_time():
    """Giving every reading the middle of the training levels is no book at
    all, and has to be beaten by a wide margin."""
    levels = [float(ln.split(",")[-1])
              for ln in TRAIN.read_text().splitlines()[1:] if ln.strip()]
    levels.sort()
    lazy_level = levels[len(levels) // 2]
    said, _elapsed, trouble = _RESULTS[0]
    assert trouble is None, trouble
    lazy = _miss([lazy_level] * len(_DRAWN[0]), _DRAWN[0])
    got = _miss(said, _DRAWN[0])
    assert got <= lazy - 1.0, (
        f"the book missed by {got:.4f} and the same level every time misses "
        f"by {lazy:.4f}")


def test_the_book_actually_reads_the_readings():
    """A book that gives the same level whatever it is handed has learned
    nothing, however close that level happens to sit."""
    said, _elapsed, trouble = _RESULTS[0]
    assert trouble is None, trouble
    assert len(set(said)) > ROWS_PER_DRAW // 100, (
        "nearly every reading came back with the same level")
