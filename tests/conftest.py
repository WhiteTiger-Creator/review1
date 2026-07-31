import hashlib
import os
import subprocess

import pytest
from expected import COLUMNS

APP = os.environ.get("PT_APP", "/app")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(TESTS_DIR, "fixtures")
ANSWER_PATH = os.path.join(APP, "answer.cypher")

# The verifier's own runner, inside the read-only test directory. The runner
# under /app/bin is agent-writable and is never executed here.
RUNNER = os.path.join(TESTS_DIR, "verifier_runner.py")

VISIBLE_GRAPH = os.path.join(APP, "graph", "argumentation.kuzu")
HIDDEN_GRAPH = os.path.join(FIX, "hidden_graph", "argumentation.kuzu")
METAMORPHIC_GRAPH = os.path.join(FIX, "metamorphic_graph", "argumentation.kuzu")

REQUIRED_COLUMNS = COLUMNS
QUERY_TIMEOUT = 600


def run_query(query_text, graph_path, timeout=QUERY_TIMEOUT):
    """Execute a query with the verifier's runner, isolated from /app."""
    env = dict(os.environ)
    env["GRAPH_DB_PATH"] = graph_path
    env["PYTHONPATH"] = ""
    proc = subprocess.run(
        ["python3", "-P", RUNNER, query_text],
        capture_output=True,
        text=True,
        env=env,
        cwd=TESTS_DIR,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        return None, None, proc.stderr
    lines = proc.stdout.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return [], set(), proc.stderr
    columns = lines[0].split("\t")
    rows = {tuple(line.split("\t")) for line in lines[1:]}
    return columns, rows, proc.stderr


def normalize_rows(columns, rows, required=REQUIRED_COLUMNS):
    missing = set(required) - set(columns)
    if missing:
        raise AssertionError(f"query result is missing columns: {missing}")
    idx = [columns.index(c) for c in required]
    return {tuple(row[i] for i in idx) for row in rows}


def rows_digest(rows):
    """SHA-256 over the sorted rows, matching how the hidden key was sealed."""
    joined = "\n".join("\t".join(row) for row in sorted(rows))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def fixture_text(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def answer_text():
    assert os.path.exists(ANSWER_PATH), "/app/answer.cypher was not written"
    with open(ANSWER_PATH, encoding="utf-8") as fh:
        text = fh.read()
    assert text.strip(), "/app/answer.cypher is empty"
    return text


@pytest.fixture(scope="session")
def answer_visible_raw(answer_text):
    return run_query(answer_text, VISIBLE_GRAPH)


@pytest.fixture(scope="session")
def answer_hidden_raw(answer_text):
    return run_query(answer_text, HIDDEN_GRAPH)


@pytest.fixture(scope="session")
def answer_visible_normalized(answer_visible_raw):
    columns, rows, err = answer_visible_raw
    assert rows is not None, f"answer query failed on the visible graph: {err}"
    return normalize_rows(columns, rows)


@pytest.fixture(scope="session")
def answer_hidden_normalized(answer_hidden_raw):
    columns, rows, err = answer_hidden_raw
    assert rows is not None, f"answer query failed on the hidden graph: {err}"
    return normalize_rows(columns, rows)


@pytest.fixture(scope="session")
def answer_metamorphic_normalized(answer_text):
    columns, rows, err = run_query(answer_text, METAMORPHIC_GRAPH)
    assert rows is not None, f"answer query failed on the metamorphic graph: {err}"
    return normalize_rows(columns, rows)
