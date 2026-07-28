import json
import os
import re
import subprocess
import sys
from fractions import Fraction

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
import tanref as R

APP = os.environ.get("QUILL_APP", "/app")
DATA_DIR = os.path.join(APP, "data")
SRC_DIR = os.path.join(APP, "src")
EX_DIR = os.path.join(APP, "examples")
BINARY = os.path.join(APP, "bin", "tan")
BATTERY = os.path.join(TESTS_DIR, "battery")
HIDDEN = os.path.join(TESTS_DIR, "hidden")
HIDDEN_DATA = os.path.join(HIDDEN, "data")

LINE_RE = re.compile(
    r"^\S+ (?:"
    r"E \d+ \d+ S \d+/\d+"
    r"|T (?:-?\d+)(?: -?\d+)*"
    r"|P \d+ C \d+ W \d+/\d+"
    r"|REJECT"
    r")$"
)

FORBIDDEN = ("golearn", "goml", "gorgonia", "gonum.org/v1/gonum/stat", "smartcore")


def _read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return [ln.rstrip("\n") for ln in fh if ln.strip() != ""]


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _group(lines):
    groups = {}
    for ln in lines:
        groups.setdefault(ln.split(" ", 1)[0], []).append(ln)
    return groups


def _fit():
    os.makedirs(os.path.join(APP, "bin"), exist_ok=True)
    return subprocess.run(
        ["go", "build", "-o", BINARY, "./src"],
        cwd=APP,
        capture_output=True,
        text=True,
        check=False,
    )


def _run(data_dir, queries_path):
    proc = subprocess.run(
        [BINARY, data_dir, queries_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("agent run failed: " + proc.stderr[-2000:])
    return [ln for ln in proc.stdout.split("\n") if ln.strip() != ""]


def _chunks(seq, count):
    size = max(1, (len(seq) + count - 1) // count)
    return [seq[i : i + size] for i in range(0, len(seq), size)]


FIT = _fit()
FIT_OK = FIT.returncode == 0 and os.path.exists(BINARY)

TABLES = R.read_tables(DATA_DIR)
HTABLES = R.read_tables(HIDDEN_DATA)

QUERY_LINES = _read_lines(os.path.join(BATTERY, "queries.txt"))
GOLDEN_LINES = _read_lines(os.path.join(BATTERY, "expected.txt"))
FAMILY = _read_json(os.path.join(BATTERY, "families.json"))

HQUERY_LINES = _read_lines(os.path.join(HIDDEN, "queries.txt"))
HGOLDEN_LINES = _read_lines(os.path.join(HIDDEN, "expected.txt"))
HFAMILY = _read_json(os.path.join(HIDDEN, "families.json"))

REF_LINES = R.process(TABLES, QUERY_LINES)
REF_BY_QID = _group(REF_LINES)
HREF_LINES = R.process(HTABLES, HQUERY_LINES)
HREF_BY_QID = _group(HREF_LINES)

QUERY_BY_QID = {ln.split()[0]: ln.split() for ln in QUERY_LINES}

if FIT_OK:
    AGENT_LINES = _run(DATA_DIR, os.path.join(BATTERY, "queries.txt"))
    HAGENT_LINES = _run(HIDDEN_DATA, os.path.join(HIDDEN, "queries.txt"))
else:
    AGENT_LINES = []
    HAGENT_LINES = []
AGENT_BY_QID = _group(AGENT_LINES)
HAGENT_BY_QID = _group(HAGENT_LINES)


def _qids(family, table):
    return sorted(q for q, f in table.items() if f == family)


BULK_QIDS = _qids("bulk", FAMILY)
EDGETIE_QIDS = _qids("edgetie", FAMILY)
CLASSTIE_QIDS = _qids("classtie", FAMILY)
REJECT_QIDS = _qids("reject", FAMILY)
HIDDEN_QIDS = sorted(HFAMILY)

DECOY = {
    v: _group(R.process(TABLES, QUERY_LINES, v)) for v in R.VARIANTS if v != "pinned"
}


def _assert_group(qids, agent_map, ref_map):
    for qid in qids:
        assert agent_map.get(qid) == ref_map.get(qid), qid


def _bins(lines):
    return [ln.split() for ln in lines if ln.split()[1] == "B"]


def test_model_sources_are_usable():
    """The model sources are complete enough to run."""
    assert FIT_OK, FIT.stderr[-2000:]


def test_reference_matches_committed_golden():
    """Independent rational recomputation equals the committed visible battery."""
    assert REF_LINES == GOLDEN_LINES


def test_hidden_reference_matches_committed_golden():
    """Independent rational recomputation equals the committed hidden battery."""
    assert HREF_LINES == HGOLDEN_LINES


def test_visible_line_count():
    """The agent emits exactly the expected number of visible battery lines."""
    assert len(AGENT_LINES) == len(REF_LINES)


def test_hidden_line_count():
    """The agent emits exactly the expected number of hidden battery lines."""
    assert len(HAGENT_LINES) == len(HREF_LINES)


def test_every_visible_query_present():
    """The agent produces an output block for every visible query id."""
    assert set(AGENT_BY_QID) == set(REF_BY_QID)


def test_every_hidden_query_present():
    """The agent produces an output block for every hidden query id."""
    assert set(HAGENT_BY_QID) == set(HREF_BY_QID)


BULK_CHUNKS = _chunks(BULK_QIDS, 20)


@pytest.mark.parametrize("idx", range(len(BULK_CHUNKS)))
def test_bulk_slice_matches(idx):
    """The agent reproduces a slice of the ordinary bulk battery exactly."""
    _assert_group(BULK_CHUNKS[idx], AGENT_BY_QID, REF_BY_QID)


EDGETIE_CHUNKS = _chunks(EDGETIE_QIDS, 3)


@pytest.mark.parametrize("idx", range(len(EDGETIE_CHUNKS)))
def test_equal_pair_score_slice_matches(idx):
    """The agent reproduces tables where two pairs score exactly alike."""
    _assert_group(EDGETIE_CHUNKS[idx], AGENT_BY_QID, REF_BY_QID)


CLASSTIE_CHUNKS = _chunks(CLASSTIE_QIDS, 3)


@pytest.mark.parametrize("idx", range(len(CLASSTIE_CHUNKS)))
def test_equal_class_score_slice_matches(idx):
    """The agent reproduces examples whose class scores come out exactly equal."""
    _assert_group(CLASSTIE_CHUNKS[idx], AGENT_BY_QID, REF_BY_QID)


def test_refused_queries_match():
    """The agent refuses exactly the queries the contract refuses."""
    _assert_group(REJECT_QIDS, AGENT_BY_QID, REF_BY_QID)


@pytest.mark.parametrize("idx", range(8))
def test_hidden_slice_matches(idx):
    """The agent generalizes to a held back battery over unseen tables."""
    chunks = _chunks(HIDDEN_QIDS, 8)
    if idx >= len(chunks):
        pytest.skip("no chunk")
    _assert_group(chunks[idx], HAGENT_BY_QID, HREF_BY_QID)


def test_line_schema_is_canonical():
    """Every emitted line matches the canonical output grammar."""
    bad = [ln for ln in AGENT_LINES + HAGENT_LINES if not LINE_RE.match(ln)]
    assert bad[:5] == []


def test_quantities_are_in_lowest_terms():
    """Every score is a reduced fraction with a positive denominator."""
    bad = []
    for ln in AGENT_LINES:
        parts = ln.split()
        tokens = (
            [parts[5]] if parts[1] == "E" else ([parts[6]] if parts[1] == "P" else [])
        )
        for token in tokens:
            num, den = token.split("/")
            value = Fraction(int(num), int(den))
            if int(den) <= 0 or f"{value.numerator}/{value.denominator}" != token:
                bad.append(ln)
    assert bad[:5] == []


def _edges(lines):
    return [ln.split() for ln in lines if ln.split()[1] == "E"]


def _tree(lines):
    rows = [ln.split() for ln in lines if ln.split()[1] == "T"]
    return [int(v) for v in rows[0][2:]] if rows else []


def test_structure_is_a_tree_over_the_features():
    """Exactly one feature is the root and the rest each carry one parent."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        query = QUERY_BY_QID[qid]
        if len(query) != 3 or query[1] not in TABLES or lines == [f"{qid} REJECT"]:
            continue
        parents = _tree(lines)
        width = len(TABLES[query[1]][0][0])
        if len(parents) != width or parents.count(-1) != 1:
            bad.append(qid)
    assert bad[:5] == []


def test_structure_has_no_cycle():
    """Following parents from any feature reaches the root without looping."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        parents = _tree(lines)
        if not parents:
            continue
        for start_node in range(len(parents)):
            seen = set()
            node = start_node
            while node != -1:
                if node in seen:
                    bad.append(qid)
                    break
                seen.add(node)
                node = parents[node]
    assert bad[:5] == []


def test_edge_count_is_one_less_than_the_features():
    """The kept dependences number exactly one fewer than the features."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        parents = _tree(lines)
        if not parents:
            continue
        if len(_edges(lines)) != len(parents) - 1:
            bad.append(qid)
    assert bad[:5] == []


def test_edges_are_reported_in_pair_order():
    """Kept dependences are listed by lower feature number then higher."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        pairs = [(int(p[2]), int(p[3])) for p in _edges(lines)]
        if pairs != sorted(pairs) or any(a >= b for a, b in pairs):
            bad.append(qid)
    assert bad[:5] == []


def test_edges_match_the_parent_structure():
    """Every kept dependence appears in the structure as a parent and child."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        parents = _tree(lines)
        if not parents:
            continue
        declared = {tuple(sorted((j, p))) for j, p in enumerate(parents) if p >= 0}
        listed = {(int(p[2]), int(p[3])) for p in _edges(lines)}
        if declared != listed:
            bad.append(qid)
    assert bad[:5] == []


def test_scores_are_never_negative():
    """No pair score is negative."""
    bad = [
        " ".join(p)
        for lines in AGENT_BY_QID.values()
        for p in _edges(lines)
        if Fraction(int(p[5].split("/")[0]), int(p[5].split("/")[1])) < 0
    ]
    assert bad[:5] == []


def test_class_scores_lie_in_the_unit_interval():
    """Every winning class score is a probability between zero and one."""
    bad = []
    for ln in AGENT_LINES:
        parts = ln.split()
        if parts[1] != "P":
            continue
        value = Fraction(int(parts[6].split("/")[0]), int(parts[6].split("/")[1]))
        if value <= 0 or value > 1:
            bad.append(ln)
    assert bad[:5] == []


def test_predicted_class_exists_in_training():
    """Every predicted class is one the training table actually carries."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        query = QUERY_BY_QID[qid]
        if len(query) != 3 or query[1] not in TABLES or lines == [f"{qid} REJECT"]:
            continue
        top = max(label for _f, label in TABLES[query[1]])
        for ln in lines:
            parts = ln.split()
            if parts[1] == "P" and not 0 <= int(parts[4]) <= top:
                bad.append(ln)
    assert bad[:5] == []


def test_every_probe_example_is_reported():
    """Each held out example gets exactly one line, in row order."""
    bad = []
    for qid, lines in AGENT_BY_QID.items():
        query = QUERY_BY_QID[qid]
        if len(query) != 3 or query[2] not in TABLES or lines == [f"{qid} REJECT"]:
            continue
        seen = [int(ln.split()[2]) for ln in lines if ln.split()[1] == "P"]
        if seen != list(range(len(TABLES[query[2]]))):
            bad.append(qid)
    assert bad[:5] == []


def test_visible_run_is_deterministic():
    """Re-running the agent on the visible battery yields identical output."""
    assert _run(DATA_DIR, os.path.join(BATTERY, "queries.txt")) == AGENT_LINES


def test_hidden_run_is_deterministic():
    """Re-running the agent on the hidden battery yields identical output."""
    assert _run(HIDDEN_DATA, os.path.join(HIDDEN, "queries.txt")) == HAGENT_LINES


def test_worked_examples_are_reproduced():
    """The agent reproduces every shipped worked example byte for byte."""
    bad = []
    for name in sorted(os.listdir(EX_DIR)):
        if not name.endswith(".in"):
            continue
        got = _run(DATA_DIR, os.path.join(EX_DIR, name))
        want = _read_lines(os.path.join(EX_DIR, name[:-3] + ".out"))
        if got != want:
            bad.append(name)
    assert bad == []


def test_no_forbidden_ml_dependency():
    """The agent sources import no bundled machine-learning library."""
    blob = ""
    for root, _dirs, files in os.walk(SRC_DIR):
        for name in sorted(files):
            with open(
                os.path.join(root, name), encoding="utf-8", errors="ignore"
            ) as fh:
                blob += fh.read().lower()
    assert [t for t in FORBIDDEN if t in blob] == []


@pytest.mark.parametrize(
    ("variant", "family"),
    [
        ("edgetie", "edgetie"),
        ("classtie", "classtie"),
    ],
)
def test_plausible_variant_fails_its_trap_family(variant, family):
    """A plausible alternative convention is wrong on the family that traps it."""
    qids = _qids(family, FAMILY)
    wrong = [q for q in qids if DECOY[variant].get(q) != REF_BY_QID.get(q)]
    assert wrong, (variant, family)


@pytest.mark.parametrize("variant", sorted(DECOY))
def test_plausible_variant_is_clean_on_bulk(variant):
    """Every alternative convention agrees on ordinary rows, so only traps separate."""
    wrong = [q for q in BULK_QIDS if DECOY[variant].get(q) != REF_BY_QID.get(q)]
    assert wrong == []


@pytest.mark.parametrize("variant", sorted(DECOY))
def test_plausible_variant_scores_zero_overall(variant):
    """Every plausible alternative convention fails the all-pass battery."""
    flat = [ln for qid in sorted(DECOY[variant]) for ln in DECOY[variant][qid]]
    assert flat != REF_LINES


def test_refusal_token_is_the_only_output():
    """A refused query emits its refusal token and nothing else."""
    for qid in REJECT_QIDS:
        assert AGENT_BY_QID.get(qid) == [f"{qid} REJECT"]


def test_battery_covers_enough_distinct_cases():
    """The executed battery carries well over the required number of semantic cases."""
    assert len(QUERY_LINES) + len(HQUERY_LINES) >= 60
    assert len(set(FAMILY.values())) >= 4
