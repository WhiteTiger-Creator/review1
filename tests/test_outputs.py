import json
import re
import shutil
import subprocess
from itertools import pairwise
from pathlib import Path

ENV = Path("/app/environment")
REPORT = Path("/app/output/residual_scope.json")
INTERIM = next((ENV / "fixtures/interim_snaps").glob("q2_*.json"))
ANNEX = ENV / "fixtures/annex"
M1 = Path("/app/output/m1_tables.rds")
COLS = ["doc_id", "win_ix", "tok_start", "tok_count", "carry_sum", "relevance"]
OUTPUT_ARTIFACTS = ("m1_" + "tables.rds", "m2_" + "witness.rds", "residual_" + "scope.json")
BUNDLES = ("w3", "w4", "k5")
TAGS = ("strict_mono", "relaxed_fast")
FOLD_ADJUSTMENT = 0.04


def _backup_outputs() -> None:
    for name in OUTPUT_ARTIFACTS:
        src = Path("/app/output") / name
        if src.exists():
            shutil.copy2(src, Path("/app/output") / f"{name}.bak")
    for src in Path("/app/output").glob(".chain_cache_*.bin"):
        shutil.copy2(src, Path("/app/output") / f"bak_{src.name}")


def _restore_outputs() -> None:
    for name in OUTPUT_ARTIFACTS:
        bak = Path("/app/output") / f"{name}.bak"
        if bak.exists():
            shutil.copy2(bak, Path("/app/output") / name)
            bak.unlink()
    for bak in Path("/app/output").glob("bak" + "_" + ".chain_cache_*.bin"):
        orig_name = bak.name[4:]
        shutil.copy2(bak, Path("/app/output") / orig_name)
        bak.unlink()


def _cleanup_backup() -> None:
    for name in OUTPUT_ARTIFACTS:
        bak = Path("/app/output") / f"{name}.bak"
        if bak.exists():
            bak.unlink()
    for bak in Path("/app/output").glob("bak" + "_" + ".chain_cache_*.bin"):
        bak.unlink()


def _load_report() -> dict:
    return json.loads(REPORT.read_text())


def _profile_field(tag: str, field: str):
    text = (ENV / "profiles" / f"{tag}.toml").read_text()
    for line in text.splitlines():
        if line.startswith(f"{field} "):
            value = line.split("=", 1)[1].strip()
            if value.startswith("["):
                return [x.strip().strip('"') for x in value.strip("[]").split(",")]
            if "." in value:
                return float(value)
            return int(value)
    raise AssertionError(f"missing {field} in {tag}")


def _residual_rows(rep: dict, bundle: str, tag: str) -> list[dict]:
    rows = rep["bundles"][bundle][tag]["residual_rows"]
    if isinstance(rows, dict):
        n = len(rows["fold"])
        return [
            {key: rows[key][i] for key in rows}
            for i in range(n)
        ]
    return rows


def _rows_in_fold_order(rows: list[dict], fold_order: list[str]) -> list[dict]:
    by_fold = {row["fold"]: row for row in rows}
    missing = [fold for fold in fold_order if fold not in by_fold]
    assert not missing, f"missing folds {missing}"
    return [by_fold[fold] for fold in fold_order]


def _assert_lowercase_hex(value: str) -> None:
    assert value == value.lower(), "chain_hex must be lowercase"
    assert re.fullmatch(r"[0-9a-f]+", value), "chain_hex must be lowercase hex digits"
    assert len(value) % 2 == 0 and len(value) > 0, "chain_hex must encode whole bytes"


def _assert_score_variation(scores: list[float], label: str) -> None:
    assert len({round(v, 6) for v in scores}) >= 2, label


def _assert_non_decreasing_scores(scores: list[float]) -> None:
    for prev, nxt in pairwise(scores):
        assert nxt - prev >= -1e-9


def _run_scope_chk() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "/app/environment/scripts/run_scope_chk.sh",
            "--suite",
            "all",
            "--tags",
            "strict_mono,relaxed_fast",
            "--bundle-out",
            "/app/output/residual_scope.json",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def _join_keys_ok(bundle: str) -> bool:
    proc = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                "source('/app/environment/lib/common_io.R'); "
                f"m1<-readRDS('/app/output/m1_tables.rds'); "
                f"jt<-read_judgments('/app/environment/fixtures/judgments/bundle_{bundle}.tsv'); "
                f"wt<-m1$window_tbls$bundle_{bundle}; "
                "cat(all(jt$doc_id %in% wt$doc_id) && nrow(wt) > 0)"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip() == "TRUE"


def _interim_relevance(bundle: str, doc_ix: int) -> float | None:
    snap = json.loads(INTERIM.read_text())
    if snap.get("bundle") != bundle or snap.get("headline_ok") is not True:
        return None
    for entry in snap["residual_rows"]:
        if int(entry["row_ix"]) == doc_ix:
            return float(entry["band"])
    return None


def _staged_relevance(bundle: str, doc_ix: int) -> float:
    proc = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                "source('/app/environment/lib/common_io.R'); "
                f"m1<-readRDS('/app/output/m1_tables.rds'); "
                f"jt<-read_judgments('/app/environment/fixtures/judgments/bundle_{bundle}.tsv'); "
                f"wt<-m1$window_tbls$bundle_{bundle}; "
                f"doc_id<-jt$doc_id[{doc_ix}]; "
                "cat(mean(wt$relevance[wt$doc_id == doc_id]))"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return float(proc.stdout.strip())


class TestOutputs:
    def test_cta01_table_shape(self) -> None:
        """Staged window tables must expose the public column layout."""
        assert M1.is_file(), "staged tables missing from pipeline output"
        proc = subprocess.run(
            ["bash", "/app/environment/scripts/inspect_cols.sh"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cols = json.loads(proc.stdout.strip())
        assert cols == COLS

    def test_cta02_join_keys(self) -> None:
        """Judgment doc_id keys must appear in staged window tables."""
        assert M1.is_file(), "staged tables missing from pipeline output"
        proc = subprocess.run(
            ["bash", "/app/environment/scripts/inspect_join.sh"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        assert proc.stdout.strip() == "TRUE"

        for bundle in BUNDLES:
            assert _join_keys_ok(bundle), f"judgment keys missing for bundle {bundle}"

        for doc_ix in (2, 5):
            band = _interim_relevance("w3", doc_ix)
            assert band is not None, f"interim snap missing row_ix {doc_ix}"
            proc = subprocess.run(
                [
                    "Rscript",
                    "-e",
                    (
                        "source('/app/environment/lib/common_io.R'); "
                        "jt<-read_judgments('/app/environment/fixtures/judgments/bundle_w3.tsv'); "
                        f"cat(jt$relevance[{doc_ix}])"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                raise AssertionError(proc.stderr)
            base = float(proc.stdout.strip())
            expected = base * (1.0 + band)
            actual = _staged_relevance("w3", doc_ix)
            assert abs(actual - expected) <= 1e-9, (
                f"w3 doc_ix {doc_ix} relevance must reflect interim band merge"
            )

        for doc_ix in (1, 3):
            proc = subprocess.run(
                [
                    "Rscript",
                    "-e",
                    (
                        "source('/app/environment/lib/common_io.R'); "
                        "jt<-read_judgments('/app/environment/fixtures/judgments/bundle_w3.tsv'); "
                        f"cat(jt$relevance[{doc_ix}])"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                raise AssertionError(proc.stderr)
            base = float(proc.stdout.strip())
            actual = _staged_relevance("w3", doc_ix)
            assert abs(actual - base) <= 1e-9, (
                f"w3 doc_ix {doc_ix} must keep unadjusted judgment relevance"
            )

    def test_cta04_bounds_row(self) -> None:
        """Witness residual magnitudes must stay inside public tolerance classes."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        for bundle in BUNDLES:
            for tag in TAGS:
                rows = _rows_in_fold_order(
                    _residual_rows(rep, bundle, tag),
                    _profile_field(tag, "fold_order"),
                )
                floor_v = float(_profile_field(tag, "residual_floor"))
                eps = float(_profile_field(tag, "band_eps"))
                base_vals = [float(row["score"]) - float(row["residual"]) for row in rows]
                base_pred = base_vals[0]
                assert all(abs(v - base_pred) <= 1e-9 for v in base_vals), (
                    f"{bundle}/{tag} residual rows must share one base_pred"
                )
                for idx, row in enumerate(rows, start=1):
                    residual = float(row["residual"])
                    score = float(row["score"])
                    assert abs(residual - (score - base_pred)) <= 1e-9
                    assert abs(residual) <= floor_v + eps + 1e-9
                    assert abs(residual) <= FOLD_ADJUSTMENT * idx + eps + 1e-9, (
                        f"{bundle}/{tag} fold {idx} residual exceeds public fold band"
                    )
                scores = [float(row["score"]) for row in rows]
                _assert_score_variation(
                    scores,
                    f"{bundle}/{tag} fold scores must not collapse to one constant",
                )

    def test_cta05_band_row(self) -> None:
        """Monotonic score ordering must hold on training folds per active profile."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        for bundle in BUNDLES:
            for tag in TAGS:
                fold_order = _profile_field(tag, "fold_order")
                rows = _rows_in_fold_order(_residual_rows(rep, bundle, tag), fold_order)
                band = float(rep["bundles"][bundle][tag]["mono_band"])
                expected = float(_profile_field(tag, "band_eps"))
                assert abs(band - expected) <= 1e-9
                base_pred = float(rows[0]["score"]) - float(rows[0]["residual"])
                scores = [float(row["score"]) for row in rows]
                assert base_pred > 0, f"{bundle}/{tag} base_pred must come from staged relevance"
                _assert_non_decreasing_scores(scores)
                _assert_score_variation(
                    scores,
                    f"{bundle}/{tag} monotonic fold scores must vary across folds",
                )

    def test_cta06_grid_row(self) -> None:
        """strict_mono and relaxed_fast suite semantics must differ as documented."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        strict_order = _profile_field("strict_mono", "fold_order")
        fast_order = _profile_field("relaxed_fast", "fold_order")
        assert strict_order != fast_order
        assert float(_profile_field("strict_mono", "band_eps")) != float(
            _profile_field("relaxed_fast", "band_eps")
        )

        seen_hex: set[str] = set()
        for bundle in BUNDLES:
            strict_hex = rep["bundles"][bundle]["strict_mono"]["chain_hex"]
            fast_hex = rep["bundles"][bundle]["relaxed_fast"]["chain_hex"]
            _assert_lowercase_hex(strict_hex)
            _assert_lowercase_hex(fast_hex)
            assert strict_hex != fast_hex, f"{bundle} tag profiles must diverge in replay digest"
            assert strict_hex not in seen_hex and fast_hex not in seen_hex, (
                f"{bundle} chain_hex must not duplicate another bundle/tag pair"
            )
            seen_hex.update({strict_hex, fast_hex})

            strict_rows = _rows_in_fold_order(
                _residual_rows(rep, bundle, "strict_mono"),
                strict_order,
            )
            fast_rows = _rows_in_fold_order(
                _residual_rows(rep, bundle, "relaxed_fast"),
                fast_order,
            )
            assert [row["fold"] for row in strict_rows] == strict_order
            assert [row["fold"] for row in fast_rows] == fast_order
            assert [float(row["score"]) for row in strict_rows] != [
                float(row["score"]) for row in fast_rows
            ], f"{bundle} witness scores must differ across active profiles"

    def test_cta07_chain_hex(self) -> None:
        """chain_hex must match hex encoding of rebuilt replay bytes for each bundle and tag."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        lengths: set[int] = set()
        for bundle in BUNDLES:
            for tag in TAGS:
                reported = rep["bundles"][bundle][tag]["chain_hex"]
                _assert_lowercase_hex(reported)
                lengths.add(len(reported))
                proc_r = subprocess.run(
                    ["bash", "/app/environment/scripts/inspect_chain.sh", bundle, tag],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if proc_r.returncode != 0:
                    raise AssertionError(proc_r.stderr)
                rebuilt = proc_r.stdout.strip()
                _assert_lowercase_hex(rebuilt)
                assert reported == rebuilt
                cache_path = Path(f"/app/output/.chain_cache_{bundle}_{tag}.bin")
                assert cache_path.is_file(), f"missing cache ledger for {bundle}/{tag}"
                assert cache_path.stat().st_size * 2 == len(reported), (
                    f"{bundle}/{tag} chain_hex must cover the full cache ledger bytes"
                )
        assert len(lengths) == 1, "all bundle/tag digests must encode the same ledger byte length"

    def test_cta08_fold_agree(self) -> None:
        """Training witness rows and certificate replay must agree on holdout folds."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        for bundle in BUNDLES:
            for tag in TAGS:
                fold_order = _profile_field(tag, "fold_order")
                rows = _rows_in_fold_order(_residual_rows(rep, bundle, tag), fold_order)
                assert len(rows) == len(fold_order)
                assert {row["fold"] for row in rows} == set(fold_order)
                base_pred = float(rows[0]["score"]) - float(rows[0]["residual"])
                scores = [float(row["score"]) for row in rows]
                for row in rows:
                    residual = float(row["residual"])
                    score = float(row["score"])
                    assert abs(residual - (score - base_pred)) <= 1e-9
                _assert_non_decreasing_scores(scores)
                _assert_score_variation(
                    scores,
                    f"{bundle}/{tag} witness scores must not be identical on every fold",
                )
                proc_r = subprocess.run(
                    ["bash", "/app/environment/scripts/inspect_mono.sh", bundle, tag],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if proc_r.returncode != 0:
                    raise AssertionError(proc_r.stderr)
                assert proc_r.stdout.strip() == "TRUE"

    def test_cta09_repeat_guard(self) -> None:
        """Repeat cache wipe without documented recovery must fail cross-run bands."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        _backup_outputs()
        try:
            wipe = subprocess.run(
                ["bash", "/app/environment/migrations/cln4.sh"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if wipe.returncode != 0:
                raise AssertionError(wipe.stderr)
            for name in OUTPUT_ARTIFACTS:
                assert not (Path("/app/output") / name).exists(), (
                    f"{name} must be removed by cache wipe"
                )
            assert not any(Path("/app/output").glob(".chain_cache_*.bin")), (
                "chain cache ledgers must be removed by cache wipe"
            )
            fail_proc = _run_scope_chk()
            if fail_proc.returncode == 0:
                raise AssertionError("expected checker failure after cache wipe")
            assert not REPORT.is_file() or fail_proc.returncode != 0
        finally:
            _restore_outputs()
            _cleanup_backup()

    def test_cta10_q4_trap(self) -> None:
        """Interim snap tallies alone must not satisfy terminal grading."""
        snap = json.loads(INTERIM.read_text())
        assert snap.get("headline_ok") is True
        assert snap.get("bundle") == "w3"
        assert snap.get("residual_rows"), "interim snap must carry historical adjustment bands"
        _backup_outputs()
        try:
            for name in OUTPUT_ARTIFACTS:
                artifact = Path("/app/output") / name
                if artifact.exists():
                    artifact.unlink()
            for cache in Path("/app/output").glob(".chain_cache_*.bin"):
                cache.unlink()
            fail_proc = _run_scope_chk()
            if fail_proc.returncode == 0:
                raise AssertionError("expected checker failure without pipeline output")
            assert not M1.is_file(), "stage_tables output must not appear without the pipeline"
            assert not Path("/app/output/m2_witness.rds").is_file()
            assert not REPORT.is_file() or fail_proc.returncode != 0
        finally:
            _restore_outputs()
            _cleanup_backup()

    def test_cta11_clean_rebuild(self) -> None:
        """Pipeline must regenerate valid outputs from scratch after a cache wipe."""
        _backup_outputs()
        try:
            subprocess.run(
                ["bash", "/app/environment/migrations/cln4.sh"],
                check=True,
                timeout=60,
            )
            subprocess.run(
                ["bash", "/app/environment/scripts/stage_tables.sh"],
                check=True,
                timeout=120,
            )
            subprocess.run(
                ["bash", "/app/environment/scripts/drive_suite.sh"],
                check=True,
                timeout=120,
            )
            proc = _run_scope_chk()
            assert proc.returncode == 0, proc.stderr
            assert M1.is_file()
            assert Path("/app/output/m2_witness.rds").is_file()
            assert REPORT.is_file()
            rep = _load_report()
            for bundle in BUNDLES:
                for tag in TAGS:
                    cache_path = Path(f"/app/output/.chain_cache_{bundle}_{tag}.bin")
                    assert cache_path.is_file(), f"missing rebuilt cache ledger for {bundle}/{tag}"
                    reported = rep["bundles"][bundle][tag]["chain_hex"]
                    proc_r = subprocess.run(
                        ["bash", "/app/environment/scripts/inspect_chain.sh", bundle, tag],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                    if proc_r.returncode != 0:
                        raise AssertionError(proc_r.stderr)
                    assert reported == proc_r.stdout.strip()
        finally:
            _restore_outputs()
            _cleanup_backup()
