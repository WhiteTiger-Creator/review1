"""Behavior checks for the journaled ship path public contract."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path("/app")
OUT = APP / "output"
SNAPS = APP / "fixtures" / "snaps"
BOOK_BASE = APP / "fixtures" / "exclbook" / "base.json"
BOOK_CHAIN = APP / "fixtures" / "exclbook" / "supersede_chain.json"
LANG_C = APP / "fixtures" / "langpacks" / "c.langpack"
LANG_DE = APP / "fixtures" / "langpacks" / "de_DE.langpack"


def _env() -> dict[str, str]:
    return os.environ.copy()


def _rebuild() -> None:
    subprocess.run(
        ["make", "-C", "/app/environment", "PREFIX=/app", "install"],
        check=True,
        capture_output=True,
        text=True,
        env=_env(),
    )


def _sha256_hex(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(data)
        path = handle.name
    try:
        completed = subprocess.run(
            ["sha256sum", path],
            check=True,
            capture_output=True,
            text=True,
            env=_env(),
        )
        return completed.stdout.split()[0]
    finally:
        os.unlink(path)


def _ship(book: Path, langpack: Path | None = None, from_unit: bool = False, fresh: bool = False) -> None:
    _rebuild()
    cmd = ["/app/scripts/run_ship.sh", "--book", str(book)]
    if langpack is not None:
        cmd.extend(["--langpack", str(langpack)])
    if from_unit:
        cmd.append("--from-unit")
    if fresh:
        cmd.append("--fresh")
    subprocess.run(cmd, check=True, env=_env())


def _check(pack: str) -> None:
    subprocess.run(["/app/bin/check_bin", "--pack", pack], check=True, env=_env())


def _canonical_number(value: float) -> str:
    return f"{value:.6f}"


def _expected_digest_for_tree(tree_id: str) -> str:
    metrics = json.loads((SNAPS / tree_id / "metrics.json").read_text(encoding="utf-8"))
    lines = []
    for row in metrics["rows"]:
        lines.append(f"{row['k']}={_canonical_number(float(row['v']))}\n")
    lines.sort()
    body = "".join(lines).encode("utf-8")
    return _sha256_hex(body)


def _read_digest() -> str:
    return (OUT / "canonical_export.sha256").read_text(encoding="utf-8").strip()


def _trace_lines() -> list[dict]:
    raw = (OUT / "reconcile_trace.jsonl").read_text(encoding="utf-8").strip()
    assert raw, "reconcile_trace.jsonl must contain at least one line"
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _read_trace() -> dict:
    return _trace_lines()[-1]


def _read_journal() -> dict:
    return json.loads((OUT / "ship_journal.json").read_text(encoding="utf-8"))


def _load_book(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_selected(book_path: Path) -> str:
    book = _load_book(book_path)
    present = {p.name for p in SNAPS.iterdir() if p.is_dir()}
    entries = [e for e in book["entries"] if e["id"] in present]
    assert entries, "book must mention at least one on-disk tree"
    best_tier = max(int(e["evidence_tier"]) for e in entries)
    top = [e for e in entries if int(e["evidence_tier"]) == best_tier]
    edges = {e["id"]: list(e.get("supersedes") or []) for e in book["entries"]}

    def reaches(src: str, dst: str) -> bool:
        seen = set()
        stack = [src]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in edges.get(cur, []):
                if nxt == dst:
                    return True
                stack.append(nxt)
        return False

    if len(top) == 1:
        return top[0]["id"]
    roots = [
        e
        for e in top
        if not any(e["id"] != other["id"] and reaches(other["id"], e["id"]) for other in top)
    ]
    pool = roots or top
    return min(e["id"] for e in pool)


def _book_stamp(path: Path) -> str:
    return _sha256_hex(path.read_bytes())


def test_repeat_emit_stable() -> None:
    """Repeated ship under C must yield an identical independently recomputed digest."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    first = _read_digest()
    _ship(BOOK_BASE, LANG_C)
    second = _read_digest()
    assert first == second
    selected = _expected_selected(BOOK_BASE)
    assert first == _expected_digest_for_tree(selected)


def test_cross_env_hash_match() -> None:
    """C, de_DE, and unit Environment runs must produce identical digest bytes."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    digest_c = _read_digest()
    _ship(BOOK_BASE, LANG_DE, fresh=True)
    digest_de = _read_digest()
    assert digest_c == digest_de
    _ship(BOOK_BASE, from_unit=True, fresh=True)
    digest_unit = _read_digest()
    assert digest_unit == digest_c
    selected = _expected_selected(BOOK_BASE)
    assert digest_c == _expected_digest_for_tree(selected)


def test_older_source_wins_when_ranked() -> None:
    """Higher evidence_tier must beat a newer low-tier snap tree."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    trace = _read_trace()
    expected = _expected_selected(BOOK_BASE)
    assert expected == "tree_a"
    assert trace["selected_id"] == expected
    assert _read_digest() == _expected_digest_for_tree(expected)
    journal = _read_journal()
    assert journal["complete"] == 1
    assert journal["book_stamp"] == _book_stamp(BOOK_BASE)
    assert journal["selected_id"] == expected
    assert journal["pack_label"] == "C"


def test_order_follows_protocol_table() -> None:
    """equal-tier supersede roots must resolve by lexicographic minimum id."""
    _ship(BOOK_CHAIN, LANG_C, fresh=True)
    trace = _read_trace()
    expected = _expected_selected(BOOK_CHAIN)
    assert expected == "tree_b"
    assert trace["selected_id"] == expected
    assert _read_digest() == _expected_digest_for_tree(expected)
    journal = _read_journal()
    assert journal["book_stamp"] == _book_stamp(BOOK_CHAIN)
    assert journal["pack_label"] == "C"


def test_torn_journal_discards_locale_stage() -> None:
    """Incomplete journal with locale-corrupted stage must not promote leftovers."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    prior_selected = _read_trace()["selected_id"]
    subprocess.run(["/app/scripts/seed_torn.sh", str(OUT)], check=True, env=_env())
    assert (OUT / "stage" / "body.txt").exists()
    assert "," in (OUT / "stage" / "body.txt").read_text(encoding="utf-8")
    _ship(BOOK_BASE, LANG_DE)
    expected = _expected_selected(BOOK_BASE)
    assert expected == "tree_a"
    lines = _trace_lines()
    assert len(lines) >= 2, "trace must accumulate across ship runs"
    assert lines[0]["selected_id"] == prior_selected
    trace = lines[-1]
    assert trace["selected_id"] == expected
    assert trace["pack_label"] == "de_DE"
    digest = _read_digest()
    assert digest == _expected_digest_for_tree(expected)
    assert "," not in (OUT / "stage" / "body.txt").read_text(encoding="utf-8")
    journal = _read_journal()
    assert int(journal["complete"]) == 1
    assert journal["book_stamp"] == _book_stamp(BOOK_BASE)
    assert journal["selected_id"] == expected
    assert journal["pack_label"] == "de_DE"
    assert journal["generation"] > 7


def test_book_flip_invalidates_completed_journal() -> None:
    """Changing the active book must invalidate a completed journal and re-select."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    assert _read_trace()["selected_id"] == "tree_a"
    _ship(BOOK_CHAIN, LANG_C)
    expected = _expected_selected(BOOK_CHAIN)
    assert expected == "tree_b"
    lines = (OUT / "reconcile_trace.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2, "trace must accumulate across ship runs"
    first = json.loads(lines[-2])
    assert first["selected_id"] == "tree_a"
    assert _read_trace()["selected_id"] == expected
    assert _read_digest() == _expected_digest_for_tree(expected)
    assert _read_journal()["book_stamp"] == _book_stamp(BOOK_CHAIN)


def test_pack_flip_invalidates_completed_journal() -> None:
    """Changing language pack with the same book must treat the journal as stale."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    first_gen = int(_read_journal()["generation"])
    digest_before = _read_digest()
    _ship(BOOK_BASE, LANG_DE)
    journal = _read_journal()
    assert journal["pack_label"] == "de_DE"
    assert journal["book_stamp"] == _book_stamp(BOOK_BASE)
    assert int(journal["generation"]) > first_gen
    assert _read_digest() == digest_before
    assert _read_digest() == _expected_digest_for_tree(_expected_selected(BOOK_BASE))
    trace = _read_trace()
    assert trace["pack_label"] == "de_DE"
    assert trace["sha_prefix"] == digest_before[:12]
    lines = _trace_lines()
    assert len(lines) >= 2
    assert lines[0]["pack_label"] == "C"


def test_coupled_torn_chain_under_locale() -> None:
    """Torn mtime-winner stage under de_DE must not beat supersede-chain selection."""
    _rebuild()
    subprocess.run(["/app/scripts/seed_torn.sh", str(OUT)], check=True, env=_env())
    _ship(BOOK_CHAIN, LANG_DE)
    expected = _expected_selected(BOOK_CHAIN)
    assert expected == "tree_b"
    trace = _read_trace()
    assert trace["selected_id"] == expected
    assert trace["pack_label"] == "de_DE"
    assert _read_digest() == _expected_digest_for_tree(expected)
    assert "," not in (OUT / "stage" / "body.txt").read_text(encoding="utf-8")
    journal = _read_journal()
    assert journal["selected_id"] == expected
    assert journal["pack_label"] == "de_DE"
    assert journal["book_stamp"] == _book_stamp(BOOK_CHAIN)
    assert journal["complete"] == 1


def test_fields_populated() -> None:
    """Trace and case-bundle entries must carry the documented non-empty fields."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    _check("C")
    trace = _read_trace()
    for key in ("event", "selected_id", "note_text", "sha_prefix", "pack_label"):
        assert key in trace
        assert isinstance(trace[key], str) and trace[key]
    assert trace["event"] == "ship_complete"
    assert trace["sha_prefix"] == _read_digest()[:12]
    assert trace["pack_label"] == "C"
    manifest = json.loads((OUT / "counterexample_archive" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cases"], "cases must be non-empty"
    case = manifest["cases"][0]
    for key in ("case_id", "selected_id", "note_text", "sha_prefix", "pack_label"):
        assert key in case
        assert isinstance(case[key], str) and case[key]
    assert case["selected_id"] == trace["selected_id"]
    assert case["sha_prefix"] == trace["sha_prefix"]
    assert case["pack_label"] == "C"
    assert case["note_text"] in trace["note_text"] or case["note_text"] == trace["note_text"]


def test_case_drops() -> None:
    """check_bin --pack must write a non-empty case-bundle aligned with digest and trace."""
    _ship(BOOK_BASE, LANG_DE, fresh=True)
    _check("de_DE")
    root = OUT / "counterexample_archive"
    manifest_path = root / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["cases"]) >= 1
    digest = _read_digest()
    trace = _read_trace()
    for case in manifest["cases"]:
        assert case["sha_prefix"] == digest[:12]
        assert case["selected_id"] == trace["selected_id"]
        assert case["pack_label"] == "de_DE"
        assert case["note_text"]
        assert case["case_id"]
    _check("de_DE")
    again = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(again["cases"]) >= 1
    assert again["cases"][0]["sha_prefix"] == digest[:12]
    assert again["cases"][0]["pack_label"] == "de_DE"


def test_unit_env_pack_label_and_generation() -> None:
    """Unit Environment path must stamp de_DE pack_label and advance generation."""
    _ship(BOOK_BASE, LANG_C, fresh=True)
    gen0 = int(_read_journal()["generation"])
    _ship(BOOK_BASE, from_unit=True)
    journal = _read_journal()
    assert journal["pack_label"] == "de_DE"
    assert int(journal["generation"]) > gen0
    assert _read_trace()["pack_label"] == "de_DE"
    assert _read_digest() == _expected_digest_for_tree(_expected_selected(BOOK_BASE))
    _check("de_DE")
    case = json.loads((OUT / "counterexample_archive" / "manifest.json").read_text(encoding="utf-8"))[
        "cases"
    ][0]
    assert case["pack_label"] == "de_DE"
