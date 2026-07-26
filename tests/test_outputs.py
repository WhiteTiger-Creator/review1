"""Behavioral verifier for reconcile-ensemble-lineage-worktrees.

The suite rebuilds the Java project offline, exercises the shipped fixture and
many generated fixtures, and compares the tool's canonical DOT / discrepancy
JSON against an independent Python lineage model. It never imports or trusts
the Java implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import case_library
import fixture_factory
import lineage_model
from lineage_model import Annotation, Edge, Manifest, Run

AUDITOR = "/app/environment"
BIN = "/app/bin/lineage-audit"
GRADLEW = "/app/environment/gradlew"
LEDGER = "/data/training-runs.csv"
DOSSIER = "/data/model-review-dossier.md"
LEFT = "/app/worktrees/rc-blue"
RIGHT = "/app/worktrees/rc-green"

SHIPPED_SEED = 20240701


# --------------------------------------------------------------------------
# Build once per session (clean, offline, from source).
# --------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def built_project():
    r = subprocess.run(
        [GRADLEW, "--offline", "--no-daemon", "clean", "test", "installDist"],
        cwd=AUDITOR,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(
            f"offline gradle build failed:\nSTDOUT\n{r.stdout}\nSTDERR\n{r.stderr}"
        )
    return True


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def run_audit(left, right, ledger, outdir, dossier=DOSSIER, extra=None):
    return subprocess.run(
        [
            BIN,
            "--left",
            str(left),
            "--right",
            str(right),
            "--ledger",
            str(ledger),
            "--dossier",
            str(dossier),
            "--output-dir",
            str(outdir),
            *(extra or []),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def edge_annotation(edges, parent, child):
    return edges[(parent, child)]["annotation"]


_ATTR = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def _unescape(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_dot(text):
    """Parse the canonical lineage.dot into run and edge dictionaries."""
    nodes = {}
    edges = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "->" in line:
            m = re.match(
                r'"((?:[^"\\]|\\.)*)"\s*->\s*"((?:[^"\\]|\\.)*)"\s*\[(.*)\];', line
            )
            if not m:
                continue
            src = _unescape(m.group(1))
            dst = _unescape(m.group(2))
            attrs = {k: _unescape(v) for k, v in _ATTR.findall(m.group(3))}
            edges[(src, dst)] = attrs
        elif line.startswith('"') and "[" in line and "graph " not in line:
            m = re.match(r'"((?:[^"\\]|\\.)*)"\s*\[(.*)\];', line)
            if not m:
                continue
            nid = _unescape(m.group(1))
            attrs = {k: _unescape(v) for k, v in _ATTR.findall(m.group(2))}
            nodes[nid] = attrs
    return nodes, edges


def expected_from_manifest(manifest):
    return lineage_model.reconcile(manifest)


def rep_diff_set(diffs):
    out = set()
    for d in diffs:
        if d["kind"] == "alias_spelling":
            out.add(("alias_spelling", d["run_uid"], tuple(sorted(d["aliases"]))))
        else:
            out.add(("annotation_placement", d["edge"], tuple(sorted(d["attributes"]))))
    return out


def check_reconciliation(dot_text, json_text, expected, expected_reps):
    nodes, edges = parse_dot(dot_text)
    report = json.loads(json_text)

    # node set + feature paths
    assert set(nodes.keys()) == {n["run_uid"] for n in expected["nodes"]}
    for n in expected["nodes"]:
        assert nodes[n["run_uid"]]["feature_path"] == n["feature_path"], n["run_uid"]
        assert nodes[n["run_uid"]]["id"] == n["run_uid"]
        assert nodes[n["run_uid"]]["label"] == n["run_uid"]

    # edge set + annotation / auc / baseline
    assert set(edges.keys()) == {(e["parent"], e["child"]) for e in expected["edges"]}
    for e in expected["edges"]:
        got = edges[(e["parent"], e["child"])]
        assert got["annotation"] == e["annotation"], (e, got)
        if "baseline" in e:
            assert got.get("baseline") == e["baseline"], (e, got)
            assert got.get("auc_delta") == e["auc_delta"], (e, got)
        else:
            assert "baseline" not in got
            assert "auc_delta" not in got

    # report counts + representation vs semantic separation
    assert report["node_count"] == expected["node_count"]
    assert report["edge_count"] == expected["edge_count"]
    assert report["semantic_discrepancies"] == []
    assert rep_diff_set(report["representation_differences"]) == expected_reps


def write_raw_worktree(base, name, dot_text, props="annotation.legacy_attrs=accept\n"):
    d = Path(base) / name
    (d / "lineage").mkdir(parents=True, exist_ok=True)
    (d / "lineage" / "graph.dot").write_text(dot_text, encoding="utf-8")
    (d / ".lineage-audit.properties").write_text(props, encoding="utf-8")
    return d


def write_raw_ledger(path, rows):
    header = fixture_factory.LEDGER_HEADER
    lines = [header]
    for r in rows:
        lines.append(",".join(r))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def outputs_absent(outdir):
    return (
        not (Path(outdir) / "lineage.dot").exists()
        and not (Path(outdir) / "discrepancies.json").exists()
    )


# --------------------------------------------------------------------------
# 1. Protected inputs unchanged
# --------------------------------------------------------------------------


def test_protected_inputs_and_contracts_unchanged():
    """Immutable inputs, docs, and worktree fixtures are unmodified and read-only."""
    manifest = json.loads(
        (Path(__file__).parent / "protected_manifest.json").read_text()
    )
    for cpath, digest in manifest["sha256"].items():
        p = Path(cpath)
        assert p.is_file(), cpath
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == digest, f"modified protected input: {cpath}"
        # Permission bits must deny write for u/g/o (os.access is unreliable as root).
        assert (p.stat().st_mode & 0o222) == 0, f"protected input is writable: {cpath}"


# --------------------------------------------------------------------------
# 2. Clean offline build + entrypoint
# --------------------------------------------------------------------------


def test_clean_offline_gradle_build_and_java_entrypoint(built_project):
    """A clean offline Gradle build succeeds and the launcher reports the version."""
    r = subprocess.run([BIN, "--version"], capture_output=True, text=True, check=False)
    assert r.returncode == 0
    assert r.stdout.strip() == "lineage-audit 1.4.2"


# --------------------------------------------------------------------------
# 3. Baseline outputs
# --------------------------------------------------------------------------


def test_baseline_outputs_parse_and_match_contracts(tmp_path):
    """Shipped audit DOT/JSON matches the lineage model contracts."""
    manifest = case_library.build_shipped_manifest()
    expected = expected_from_manifest(manifest)
    with tempfile.TemporaryDirectory() as td:
        reps = fixture_factory.write_worktrees(Path(td), manifest, seed=SHIPPED_SEED)
        expected_reps = rep_diff_set(reps["representation_differences"])
    out = tmp_path / "out"
    r = run_audit(LEFT, RIGHT, LEDGER, out)
    assert r.returncode == 0, r.stderr
    summary = "lineage-audit: reconciled {} nodes, {} edges".format(
        expected["node_count"], expected["edge_count"]
    )
    assert r.stdout.strip() == summary
    assert r.stderr == ""
    dot_text = (out / "lineage.dot").read_text()
    json_text = (out / "discrepancies.json").read_text()
    check_reconciliation(dot_text, json_text, expected, expected_reps)
    # DOT must parse with Graphviz
    canon = subprocess.run(
        ["dot", "-Tcanon", str(out / "lineage.dot")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert canon.returncode == 0, canon.stderr


# --------------------------------------------------------------------------
# 4-9. Generated valid fixtures (identity, annotation, feature paths, AUC,
#      representation vs semantic, escapes).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", list(range(12)))
def test_generated_cases_match_policy_model(seed, tmp_path):
    """Generated lineages match the lineage model contracts."""
    manifest = case_library.random_valid_manifest(seed)
    expected = expected_from_manifest(manifest)
    base = tmp_path / f"case{seed}"
    base.mkdir()
    reps = fixture_factory.write_worktrees(base, manifest, seed=seed + 100)
    out = base / "out"
    r = run_audit(reps["left"], reps["right"], reps["ledger"], out)
    assert r.returncode == 0, r.stderr
    check_reconciliation(
        (out / "lineage.dot").read_text(),
        (out / "discrepancies.json").read_text(),
        expected,
        rep_diff_set(reps["representation_differences"]),
    )


@pytest.mark.parametrize("seed", [7, 21, 42])
def test_quoted_ids_escapes_and_repeated_attribute_lists(seed, tmp_path):
    """Quoted escaped Unicode IDs resolve and parse with Graphviz."""
    manifest = case_library.random_valid_manifest(seed, weird_aliases=True)
    expected = expected_from_manifest(manifest)
    base = tmp_path / f"weird{seed}"
    base.mkdir()
    reps = fixture_factory.write_worktrees(base, manifest, seed=seed + 500)
    out = base / "out"
    r = run_audit(reps["left"], reps["right"], reps["ledger"], out)
    assert r.returncode == 0, r.stderr
    check_reconciliation(
        (out / "lineage.dot").read_text(),
        (out / "discrepancies.json").read_text(),
        expected,
        rep_diff_set(reps["representation_differences"]),
    )
    canon = subprocess.run(
        ["dot", "-Tcanon", str(out / "lineage.dot")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert canon.returncode == 0, canon.stderr


# --------------------------------------------------------------------------
# 10. Source order / swap invariance + repeated-run determinism.
# --------------------------------------------------------------------------


def test_source_order_swap_and_repeat_determinism(tmp_path):
    """Repeated and swapped runs are byte-identical without path leakage."""
    o1 = tmp_path / "o1"
    o2 = tmp_path / "o2"
    o3 = tmp_path / "o3"
    assert run_audit(LEFT, RIGHT, LEDGER, o1).returncode == 0
    assert run_audit(LEFT, RIGHT, LEDGER, o2).returncode == 0
    assert run_audit(RIGHT, LEFT, LEDGER, o3).returncode == 0  # swapped
    for name in ("lineage.dot", "discrepancies.json"):
        b1 = (o1 / name).read_bytes()
        assert b1 == (o2 / name).read_bytes(), f"repeat run differs: {name}"
        assert b1 == (o3 / name).read_bytes(), f"swap run differs: {name}"
        text = b1.decode()
        assert (
            "/tmp" not in text and "/app" not in text and "gradle" not in text.lower()
        )
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text)


# --------------------------------------------------------------------------
# 11. CLI vs branch config precedence.
# --------------------------------------------------------------------------


def _precedence_manifest():

    runs = {
        "pc-01": Run(
            "pc-01",
            "PR-01",
            "PL-01",
            "train",
            "released",
            "cohortA",
            "fs-a",
            "0.800000",
        ),
        "pc-02": Run(
            "pc-02",
            "PR-02",
            "PL-02",
            "train",
            "released",
            "cohortA",
            "fs-b",
            "0.820000",
        ),
    }
    edges = [
        Edge(
            "pc-01",
            "pc-02",
            [
                Annotation("proposal", "2024-01-10", "warmstart"),
                Annotation("approved", "2025-02-01", "feature_inheritance"),
            ],
        )
    ]
    return Manifest(runs=runs, edges=edges)


def test_cli_and_branch_config_precedence(tmp_path):
    """CLI overrides beat branch properties and packaged defaults."""
    manifest = _precedence_manifest()
    base = tmp_path / "prec"
    base.mkdir()
    reps = fixture_factory.write_worktrees(base, manifest, seed=999)
    # Force both branches to strict: only `label` (left/proposal) would count.
    for name in ("rc-blue", "rc-green"):
        (base / name / ".lineage-audit.properties").write_text(
            "annotation.legacy_attrs=strict\n", encoding="utf-8"
        )

    # CLI override accept must win over branch strict -> approved (xlabel) honored.
    out_accept = base / "accept"
    r = run_audit(
        reps["left"],
        reps["right"],
        reps["ledger"],
        out_accept,
        extra=["--set", "annotation.legacy_attrs=accept"],
    )
    assert r.returncode == 0, r.stderr
    _, edges = parse_dot((out_accept / "lineage.dot").read_text())
    assert edge_annotation(edges, "pc-01", "pc-02") == "feature_inheritance"

    # No CLI override: branch strict wins -> only the proposal in `label`.
    out_strict = base / "strict"
    r2 = run_audit(reps["left"], reps["right"], reps["ledger"], out_strict)
    assert r2.returncode == 0, r2.stderr
    _, edges2 = parse_dot((out_strict / "lineage.dot").read_text())
    assert edge_annotation(edges2, "pc-01", "pc-02") == "warmstart"


# --------------------------------------------------------------------------
# 12. Ambiguous alias rejected atomically.
# --------------------------------------------------------------------------


def test_ambiguous_alias_rejected_atomically(tmp_path):
    """Ambiguous aliases exit 2 with no output files."""
    base = tmp_path / "amb"
    base.mkdir()
    write_raw_ledger(
        base / "ledger.csv",
        [
            [
                "run-a",
                "DUP",
                "AX",
                "",
                "train",
                "released",
                "cohortA",
                "fs-a",
                "0.80",
                "cards/a.md",
            ],
            [
                "run-b",
                "BX",
                "DUP",
                "",
                "train",
                "released",
                "cohortA",
                "fs-b",
                "0.81",
                "cards/b.md",
            ],
        ],
    )
    dot = 'digraph g { "DUP"; }\n'
    left = write_raw_worktree(base, "rc-blue", dot)
    right = write_raw_worktree(base, "rc-green", dot)
    out = base / "out"
    out.mkdir()
    r = run_audit(left, right, base / "ledger.csv", out)
    assert r.returncode == 2, r.stderr
    assert "AMBIGUOUS_ALIAS" in r.stderr
    assert r.stdout == ""
    assert outputs_absent(out)


# --------------------------------------------------------------------------
# 13. Conflicting parentage / metrics rejected atomically.
# --------------------------------------------------------------------------


def test_conflicting_parentage_rejected_atomically(tmp_path):
    """Conflicting parents exit 3 with no outputs."""
    base = tmp_path / "confp"
    base.mkdir()
    write_raw_ledger(
        base / "ledger.csv",
        [
            [
                "run-p",
                "P0",
                "P1",
                "",
                "train",
                "released",
                "cohortA",
                "fs-a",
                "0.80",
                "cards/p.md",
            ],
            [
                "run-c",
                "C0",
                "C1",
                "run-p",
                "train",
                "released",
                "cohortA",
                "fs-b",
                "0.81",
                "cards/c.md",
            ],
            [
                "run-d",
                "D0",
                "D1",
                "run-p",
                "train",
                "released",
                "cohortA",
                "fs-c",
                "0.82",
                "cards/d.md",
            ],
        ],
    )
    left = write_raw_worktree(
        base,
        "rc-blue",
        'digraph g { "P0" -> "C0" [label="approved|2025-01-01|warmstart"]; }\n',
    )
    right = write_raw_worktree(
        base,
        "rc-green",
        'digraph g { "P1" -> "D1" [xlabel="approved|2025-01-01|warmstart"]; }\n',
    )
    out = base / "out"
    out.mkdir()
    r = run_audit(left, right, base / "ledger.csv", out)
    assert r.returncode == 3, r.stderr
    assert "CONFLICTING_PARENTAGE" in r.stderr
    assert outputs_absent(out)


def test_conflicting_metrics_rejected_atomically(tmp_path):
    """Conflicting metrics exit 3 with no outputs."""
    base = tmp_path / "confm"
    base.mkdir()
    write_raw_ledger(
        base / "ledger.csv",
        [
            [
                "run-p",
                "P0",
                "P1",
                "",
                "train",
                "released",
                "cohortA",
                "fs-a",
                "0.80",
                "cards/p.md",
            ],
            [
                "run-c",
                "C0",
                "C1",
                "run-p",
                "train",
                "released",
                "cohortA",
                "fs-b",
                "0.81",
                "cards/c.md",
            ],
        ],
    )
    left = write_raw_worktree(
        base,
        "rc-blue",
        (
            'digraph g { "P0" [auc="0.800000"]; '
            '"P0" -> "C0" [label="approved|2025-01-01|warmstart"]; }\n'
        ),
    )
    right = write_raw_worktree(
        base,
        "rc-green",
        (
            'digraph g { "P1" [auc="0.700000"]; '
            '"P1" -> "C1" [xlabel="approved|2025-01-01|warmstart"]; }\n'
        ),
    )
    out = base / "out"
    out.mkdir()
    r = run_audit(left, right, base / "ledger.csv", out)
    assert r.returncode == 3, r.stderr
    assert "CONFLICTING_METRICS" in r.stderr
    assert outputs_absent(out)


# --------------------------------------------------------------------------
# 14. Missing run / malformed DOT fail without partial outputs.
# --------------------------------------------------------------------------


def test_unknown_run_rejected(tmp_path):
    """Unknown runs exit 2 with no output files."""
    base = tmp_path / "unk"
    base.mkdir()
    write_raw_ledger(
        base / "ledger.csv",
        [
            [
                "run-p",
                "P0",
                "P1",
                "",
                "train",
                "released",
                "cohortA",
                "fs-a",
                "0.80",
                "cards/p.md",
            ],
        ],
    )
    dot = 'digraph g { "GHOST" -> "P0" [label="approved|2025-01-01|warmstart"]; }\n'
    left = write_raw_worktree(base, "rc-blue", dot)
    right = write_raw_worktree(base, "rc-green", dot)
    out = base / "out"
    out.mkdir()
    r = run_audit(left, right, base / "ledger.csv", out)
    assert r.returncode == 2, r.stderr
    assert "UNKNOWN_RUN" in r.stderr
    assert outputs_absent(out)


def test_malformed_dot_rejected(tmp_path):
    """A syntactically invalid DOT worktree exits 2 (MALFORMED_DOT) with no outputs."""
    base = tmp_path / "mal"
    base.mkdir()
    write_raw_ledger(
        base / "ledger.csv",
        [
            [
                "run-p",
                "P0",
                "P1",
                "",
                "train",
                "released",
                "cohortA",
                "fs-a",
                "0.80",
                "cards/p.md",
            ],
        ],
    )
    left = write_raw_worktree(base, "rc-blue", 'digraph g { "P0" -> ; }\n')
    right = write_raw_worktree(base, "rc-green", 'digraph g { "P1"; }\n')
    out = base / "out"
    out.mkdir()
    r = run_audit(left, right, base / "ledger.csv", out)
    assert r.returncode == 2, r.stderr
    assert "MALFORMED_DOT" in r.stderr
    assert outputs_absent(out)


# --------------------------------------------------------------------------
# 15. Legacy CLI help / version / validation.
# --------------------------------------------------------------------------


def test_legacy_cli_help_version_and_validation_contract(tmp_path):
    """Help version and validation follow the documented CLI contract."""
    h = subprocess.run([BIN, "--help"], capture_output=True, text=True, check=False)
    assert h.returncode == 0
    assert "usage: lineage-audit" in h.stdout

    v = subprocess.run([BIN, "--version"], capture_output=True, text=True, check=False)
    assert v.returncode == 0 and v.stdout.strip() == "lineage-audit 1.4.2"

    miss = subprocess.run(
        [BIN, "--left", LEFT], capture_output=True, text=True, check=False
    )
    assert miss.returncode == 1
    assert "usage: lineage-audit" in miss.stderr

    unk = subprocess.run([BIN, "--bogus"], capture_output=True, text=True, check=False)
    assert unk.returncode == 1

    out = tmp_path / "out"
    bad = run_audit(LEFT, RIGHT, "/data/does-not-exist.csv", out)
    assert bad.returncode == 1
    assert outputs_absent(out)


# --------------------------------------------------------------------------
# 16. No fixture-specific constants / output shortcut.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1000, 2000, 3000, 4000, 5000])
def test_no_hardcoding_across_unrelated_families(seed, tmp_path):
    """Unrelated run-id families still reconcile without shipped-answer hardcoding."""
    manifest = case_library.random_valid_manifest(seed)
    expected = expected_from_manifest(manifest)
    base = tmp_path / f"fam{seed}"
    base.mkdir()
    reps = fixture_factory.write_worktrees(base, manifest, seed=seed)
    out = base / "out"
    r = run_audit(reps["left"], reps["right"], reps["ledger"], out)
    assert r.returncode == 0, r.stderr
    check_reconciliation(
        (out / "lineage.dot").read_text(),
        (out / "discrepancies.json").read_text(),
        expected,
        rep_diff_set(reps["representation_differences"]),
    )
