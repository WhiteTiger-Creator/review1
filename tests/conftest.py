"""Shared helpers for umber-kiln-parcel-engraver verifier tests."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
PARCELS = APP / "parcels"
OUT = APP / "out"
TMP = APP / "engraving_tmp"
CASES = PARCELS / "cases"
INDEX = OUT / "crate.index"
MANIFEST = OUT / "seal.manifest"

SHEETS = [
    "stamps.tsv",
    "crates.tsv",
    "shards.tsv",
    "mirrors.tsv",
    "notices.tsv",
    "lanes.tsv",
    "checksums.tsv",
    "tiers.tsv",
    "widths.tsv",
]

INDEX_WIDTHS = {
    "crate_id": 10,
    "family": 10,
    "shard_count": 4,
    "byte_total": 8,
    "lane_id": 8,
    "release_tier": 12,
    "index_note": 8,
}

MANIFEST_WIDTHS = {
    "crate_id": 10,
    "seal_token": 12,
    "mirror_id": 10,
    "notice_fence": 12,
    "checksum_alphabet": 10,
    "public_seal_text": 40,
}

# Right-aligned numeric columns on crate.index
INDEX_RIGHT_ALIGN = {"shard_count", "byte_total"}

INDEX_HEADER = "crate_id family shard_count byte_total lane_id release_tier index_note"
MANIFEST_HEADER = (
    "crate_id seal_token mirror_id notice_fence checksum_alphabet public_seal_text"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parcel_digests() -> dict[str, str]:
    return {name: sha256_file(PARCELS / name) for name in SHEETS if (PARCELS / name).exists()}


def clear_outputs() -> None:
    for p in (INDEX, MANIFEST):
        if p.exists():
            p.unlink()


def copy_case(name: str) -> None:
    src = CASES / name
    assert src.is_dir(), f"missing case {name}"
    for table in SHEETS:
        source = src / table
        if source.exists():
            shutil.copy2(source, PARCELS / table)


def run_engrave() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-C", str(APP), "engrave", f"PARCELS={PARCELS}", f"OUT={OUT}"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        check=False,
    )


def run_clean() -> None:
    subprocess.run(["make", "-C", str(APP), "clean"], check=True, capture_output=True)


def assert_tmp_clean() -> None:
    leftovers = [p.name for p in TMP.iterdir() if p.name != ".keep"]
    assert leftovers == [], f"engraving_tmp scraps remain: {leftovers}"


def assert_only_products() -> None:
    names = sorted(p.name for p in OUT.iterdir() if p.name != ".keep")
    assert names == ["crate.index", "seal.manifest"], names


def assert_no_products() -> None:
    assert not INDEX.exists()
    assert not MANIFEST.exists()
    names = [p.name for p in OUT.iterdir() if p.name != ".keep"]
    assert names == [], names


def expect_success(case: str) -> tuple[str, str]:
    copy_case(case)
    run_clean()
    proc = run_engrave()
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert INDEX.is_file() and MANIFEST.is_file()
    assert_tmp_clean()
    assert_only_products()
    return INDEX.read_text(encoding="utf-8"), MANIFEST.read_text(encoding="utf-8")


def expect_failure(case: str) -> None:
    copy_case(case)
    OUT.mkdir(parents=True, exist_ok=True)
    INDEX.write_text("STALE\n", encoding="utf-8")
    MANIFEST.write_text("STALE\n", encoding="utf-8")
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / "scrap.tmp").write_text("x", encoding="utf-8")
    proc = run_engrave()
    assert proc.returncode != 0, "expected inconsistent set to fail"
    assert_no_products()
    assert_tmp_clean()


def parse_fixed(
    text: str,
    header: str,
    widths: dict[str, int],
    right_align: set[str] | None = None,
) -> list[dict[str, str]]:
    right_align = right_align or set()
    lines = text.splitlines()
    assert lines, "empty product"
    assert lines[0] == header
    rows = []
    for line in lines[1:]:
        i = 0
        row = {}
        for col, w in widths.items():
            raw = line[i : i + w]
            assert len(raw) == w, f"{col} truncated: {raw!r}"
            stripped = raw.strip(" ")
            if col in right_align:
                # strip()+rjust catches left-aligned fields with trailing spaces
                assert raw == stripped.rjust(w), f"{col} not right-aligned: {raw!r}"
                row[col] = stripped
            else:
                assert raw == stripped.ljust(w), f"{col} not left-aligned: {raw!r}"
                row[col] = stripped
            i += w
        assert i == len(line), f"width mismatch: {line!r} len={len(line)} expected={i}"
        rows.append(row)
    return rows


def parse_index(text: str) -> list[dict[str, str]]:
    return parse_fixed(text, INDEX_HEADER, INDEX_WIDTHS, INDEX_RIGHT_ALIGN)


def parse_manifest(text: str) -> list[dict[str, str]]:
    return parse_fixed(text, MANIFEST_HEADER, MANIFEST_WIDTHS)


def assert_lf_final_newline(text: str) -> None:
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def load_tsv(path: Path) -> list[dict[str, str]]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    headers = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        rows.append({headers[i]: (cols[i] if i < len(cols) else "").strip() for i in range(len(headers))})
    return rows


def shard_totals(case_dir: Path) -> dict[str, tuple[int, int]]:
    totals: dict[str, list[int]] = {}
    for row in load_tsv(case_dir / "shards.tsv"):
        cid = row["crate_id"]
        totals.setdefault(cid, [0, 0])
        totals[cid][0] += 1
        totals[cid][1] += int(row["byte_count"])
    return {k: (v[0], v[1]) for k, v in totals.items()}


def choose_mirror(case_dir: Path, crate_id: str) -> str:
    """Dominant shard, then lowest priority, then crate-wide affinity, then id."""
    shards = [r for r in load_tsv(case_dir / "shards.tsv") if r["crate_id"] == crate_id]
    assert shards, f"no shards for {crate_id}"
    dominant = min(shards, key=lambda s: (-int(s["byte_count"]), int(s["shard_order"])))
    mirrors = load_tsv(case_dir / "mirrors.tsv")

    def covers_all(mirror_id: str) -> bool:
        for s in shards:
            ok = False
            for m in mirrors:
                if (
                    m["mirror_id"] == mirror_id
                    and m["input_name"] == s["input_name"]
                    and m["mirror_trust"] == "yes"
                    and m["receipt_digest"] == s["shard_digest"]
                ):
                    ok = True
                    break
            if not ok:
                return False
        return True

    best = None
    for m in mirrors:
        if m["input_name"] != dominant["input_name"]:
            continue
        if m["mirror_trust"] != "yes":
            continue
        if m["receipt_digest"] != dominant["shard_digest"]:
            continue
        cand = (int(m["mirror_priority"]), 0 if covers_all(m["mirror_id"]) else 1, m["mirror_id"])
        if best is None or cand < best:
            best = cand
    assert best is not None, f"no mirror for dominant shard of {crate_id}"
    return best[2]


@pytest.fixture()
def clean_workspace():
    run_clean()
    clear_outputs()
    TMP.mkdir(parents=True, exist_ok=True)
    yield
    run_clean()
