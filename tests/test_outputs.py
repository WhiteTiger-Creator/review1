import json
import re
import shutil
import subprocess
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
    for i in range(len(scores) - 1):
        prev, nxt = scores[i], scores[i + 1]
        assert nxt - prev >= 1e-9


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
        """All bundle window tables must expose the public column layout with correct types;
        carry_sum must be a running cumulative total (strictly increasing per window within
        a document traversal); tok_start for each window must equal the preceding window's
        tok_start plus tok_count."""
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

        # All three bundle window tables must expose the EXACT same column set and order
        for bundle in BUNDLES:
            proc2 = subprocess.run(
                [
                    "Rscript",
                    "-e",
                    (
                        "m1<-readRDS('/app/output/m1_tables.rds'); "
                        f"wt<-m1$window_tbls$bundle_{bundle}; "
                        "library(jsonlite); "
                        "cat(toJSON(colnames(wt), auto_unbox=TRUE))"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc2.returncode != 0:
                raise AssertionError(proc2.stderr)
            bundle_cols = json.loads(proc2.stdout.strip())
            assert bundle_cols == COLS, (
                f"bundle_{bundle} columns {bundle_cols} must match public layout {COLS}"
            )

        # Verify column types for all bundles
        for bundle in BUNDLES:
            type_check_proc = subprocess.run(
                [
                    "Rscript",
                    "-e",
                    (
                        "m1<-readRDS('/app/output/m1_tables.rds'); "
                        f"wt<-m1$window_tbls$bundle_{bundle}; "
                        "ok <- is.character(wt$doc_id) && "
                        "      is.integer(wt$win_ix) && "
                        "      is.integer(wt$tok_start) && "
                        "      is.integer(wt$tok_count) && "
                        "      is.numeric(wt$carry_sum) && "
                        "      is.numeric(wt$relevance); "
                        "cat(ok)"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if type_check_proc.returncode != 0:
                raise AssertionError(type_check_proc.stderr)
            assert type_check_proc.stdout.strip() == "TRUE", (
                f"bundle_{bundle} column types must match public layout specification"
            )

        # Verify tok_start[i] == tok_start[i-1] + tok_count[i-1] (contiguous windows),
        # carry_sum must be strictly increasing (each window accumulates more tokens),
        # win_ix must start at 0 and increment by exactly 1 each row.
        arithmetic_proc = subprocess.run(
            [
                "Rscript",
                "-e",
                (
                    "m1<-readRDS('/app/output/m1_tables.rds'); "
                    "wt<-m1$window_tbls$bundle_w3; "
                    "n<-nrow(wt); "
                    # tok_start[i] == tok_start[i-1] + tok_count[i-1]
                    "cont_ok <- if (n > 1) all(wt$tok_start[2:n] == "
                    "  (wt$tok_start[1:(n-1)] + wt$tok_count[1:(n-1)])) else TRUE; "
                    # carry_sum strictly increasing
                    "carry_ok <- if (n > 1) all(diff(wt$carry_sum) > 0) else TRUE; "
                    # win_ix = 0-based sequential
                    "winix_ok <- all(wt$win_ix == seq(0L, n - 1L)); "
                    "cat(cont_ok && carry_ok && winix_ok)"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if arithmetic_proc.returncode != 0:
            raise AssertionError(arithmetic_proc.stderr)
        assert arithmetic_proc.stdout.strip() == "TRUE", (
            "bundle_w3 window arithmetic violated: "
            "tok_start must be contiguous, carry_sum strictly increasing, win_ix sequential"
        )

        # carry_sum for row i must equal the cumulative sum of tok_count through row i
        cumsum_proc = subprocess.run(
            [
                "Rscript",
                "-e",
                (
                    "m1<-readRDS('/app/output/m1_tables.rds'); "
                    "wt<-m1$window_tbls$bundle_w3; "
                    "expected_carry<-cumsum(wt$tok_count); "
                    "cat(all(abs(wt$carry_sum - expected_carry) < 1e-9))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if cumsum_proc.returncode != 0:
            raise AssertionError(cumsum_proc.stderr)
        assert cumsum_proc.stdout.strip() == "TRUE", (
            "bundle_w3 carry_sum must equal cumsum(tok_count): "
            "each row's carry_sum is the running token total through that window"
        )

    def test_cta02_join_keys(self) -> None:
        """Judgment doc_id keys must appear in all staged window tables; interim band merges
        must be exact and strictly isolated to the correct bundle; band scaling applies only
        to the specific row_ix positions listed in the snap, not to all windows of that doc."""
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

        snap = json.loads(INTERIM.read_text())
        assert snap.get("headline_ok") is True, "interim snap must have headline_ok=true"
        snap_bands = {int(e["row_ix"]): float(e["band"]) for e in snap["residual_rows"]}

        # Snapped rows must have relevance = base * (1 + band) — exact, no tolerance creep
        for doc_ix in sorted(snap_bands.keys()):
            band = snap_bands[doc_ix]
            base_proc = subprocess.run(
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
            if base_proc.returncode != 0:
                raise AssertionError(base_proc.stderr)
            base = float(base_proc.stdout.strip())
            expected = base * (1.0 + band)
            actual = _staged_relevance("w3", doc_ix)
            assert abs(actual - expected) <= 1e-9, (
                f"w3 doc_ix {doc_ix}: staged relevance {actual} != base*(1+band) = {expected}"
            )

        # Unadjusted rows (all non-snapped doc_ix) must keep raw relevance exactly
        w3_doc_count_proc = subprocess.run(
            [
                "Rscript",
                "-e",
                (
                    "source('/app/environment/lib/common_io.R'); "
                    "jt<-read_judgments('/app/environment/fixtures/judgments/bundle_w3.tsv'); "
                    "cat(nrow(jt))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if w3_doc_count_proc.returncode != 0:
            raise AssertionError(w3_doc_count_proc.stderr)
        w3_doc_count = int(w3_doc_count_proc.stdout.strip())
        unadjusted = [i for i in range(1, w3_doc_count + 1) if i not in snap_bands]
        check_set = (unadjusted[:2] + unadjusted[-2:]) if len(unadjusted) >= 4 else unadjusted
        for doc_ix in check_set:
            raw_proc = subprocess.run(
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
            if raw_proc.returncode != 0:
                raise AssertionError(raw_proc.stderr)
            base = float(raw_proc.stdout.strip())
            actual = _staged_relevance("w3", doc_ix)
            assert abs(actual - base) <= 1e-9, (
                f"w3 doc_ix {doc_ix} (not in snap) must keep raw relevance {base}; got {actual}"
            )

        # Snap is w3-only: w4 and k5 must not be contaminated at any row_ix
        for other_bundle in ("w4", "k5"):
            for doc_ix in sorted(snap_bands.keys()):
                raw_proc = subprocess.run(
                    [
                        "Rscript",
                        "-e",
                        (
                            "source('/app/environment/lib/common_io.R'); "
                            f"jt<-read_judgments('/app/environment/fixtures/judgments/bundle_{other_bundle}.tsv'); "
                            f"n<-nrow(jt); ix<-min({doc_ix}, n); cat(jt$relevance[ix])"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if raw_proc.returncode != 0:
                    raise AssertionError(raw_proc.stderr)
                base = float(raw_proc.stdout.strip())
                actual_proc = subprocess.run(
                    [
                        "Rscript",
                        "-e",
                        (
                            "source('/app/environment/lib/common_io.R'); "
                            f"m1<-readRDS('/app/output/m1_tables.rds'); "
                            f"jt<-read_judgments('/app/environment/fixtures/judgments/bundle_{other_bundle}.tsv'); "
                            f"wt<-m1$window_tbls$bundle_{other_bundle}; "
                            f"n<-nrow(jt); ix<-min({doc_ix}, n); "
                            "doc_id<-jt$doc_id[ix]; "
                            "cat(mean(wt$relevance[wt$doc_id == doc_id]))"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if actual_proc.returncode != 0:
                    raise AssertionError(actual_proc.stderr)
                actual = float(actual_proc.stdout.strip())
                assert abs(actual - base) <= 1e-9, (
                    f"{other_bundle} doc_ix {doc_ix} contaminated by w3-only snap; "
                    f"got {actual}, expected {base}"
                )

    def test_cta04_bounds_row(self) -> None:
        """Residual magnitudes must respect the global floor+eps bound; base_pred must equal
        mean staged window relevance (computed per-bundle from R); fold-index cumulative band
        limit is derived from the fold_adjustment constant embedded in scope_rules.md
        (fold_adjustment * fold_index_1based + band_eps)."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()

        # The fold_adjustment constant (0.04) is documented in scope_rules.md under
        # "Monotonic Constraint Optimization". Read and confirm it is mentioned.
        scope_rules = (ENV / "docs" / "scope_rules.md").read_text()
        assert "0.04" in scope_rules, (
            "fold_adjustment=0.04 must be documented in scope_rules.md"
        )
        # Derive fold_adjustment from scope_rules.md: line containing "0.04 * fold_index"
        fold_adj_line = next(
            (ln for ln in scope_rules.splitlines() if "0.04" in ln and "fold" in ln.lower()),
            None,
        )
        assert fold_adj_line is not None, (
            "scope_rules.md must document the fold_adjustment formula with 0.04"
        )
        fold_adjustment = 0.04  # from scope_rules.md

        for bundle in BUNDLES:
            for tag in TAGS:
                rows = _rows_in_fold_order(
                    _residual_rows(rep, bundle, tag),
                    _profile_field(tag, "fold_order"),
                )
                floor_v = float(_profile_field(tag, "residual_floor"))
                eps = float(_profile_field(tag, "band_eps"))
                bound = floor_v + eps

                base_vals = [float(row["score"]) - float(row["residual"]) for row in rows]
                assert len(base_vals) >= 2, f"{bundle}/{tag} must have at least 2 fold rows"
                base_pred = base_vals[0]
                for i, v in enumerate(base_vals):
                    assert abs(v - base_pred) <= 1e-9, (
                        f"{bundle}/{tag} fold {i+1}: base_pred inconsistent across rows"
                    )

                for idx, row in enumerate(rows, start=1):
                    residual = float(row["residual"])
                    score = float(row["score"])
                    assert abs(residual - (score - base_pred)) <= 1e-9
                    assert abs(residual) <= bound + 1e-9, (
                        f"{bundle}/{tag} fold {idx}: |residual| exceeds floor+eps bound"
                    )
                    per_fold_limit = fold_adjustment * idx + eps
                    assert abs(residual) <= per_fold_limit + 1e-9, (
                        f"{bundle}/{tag} fold {idx}: |residual|={abs(residual)} "
                        f"exceeds per-fold limit {fold_adjustment}*{idx}+{eps}={per_fold_limit}"
                    )

                scores = [float(row["score"]) for row in rows]
                _assert_score_variation(scores, f"{bundle}/{tag} fold scores must vary")
                assert base_pred > 0, f"{bundle}/{tag} base_pred must be positive"

                # base_pred must equal mean staged window relevance — no hardcoding allowed
                mean_rel_proc = subprocess.run(
                    [
                        "Rscript",
                        "-e",
                        (
                            "source('/app/environment/lib/common_io.R'); "
                            f"m1<-readRDS('/app/output/m1_tables.rds'); "
                            f"wt<-m1$window_tbls$bundle_{bundle}; "
                            "cat(mean(wt$relevance))"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if mean_rel_proc.returncode != 0:
                    raise AssertionError(mean_rel_proc.stderr)
                mean_rel = float(mean_rel_proc.stdout.strip())
                assert abs(base_pred - mean_rel) <= 1e-9, (
                    f"{bundle}/{tag} base_pred={base_pred} must equal mean staged relevance={mean_rel}"
                )

    def test_cta05_band_row(self) -> None:
        """Monotonic score ordering must hold strictly between EVERY adjacent fold pair with
        gap >= 1e-9; mono_band must equal band_eps from profile; fold names in report rows
        must match profile fold_order exactly; cross-bundle base_pred ordering must reflect
        their distinct mean relevance values."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()

        # Collect base_pred per bundle (mean relevance) — they must be distinct across bundles
        bundle_base_preds: dict[str, float] = {}
        for bundle in BUNDLES:
            mean_proc = subprocess.run(
                [
                    "Rscript",
                    "-e",
                    (
                        "source('/app/environment/lib/common_io.R'); "
                        f"m1<-readRDS('/app/output/m1_tables.rds'); "
                        f"wt<-m1$window_tbls$bundle_{bundle}; "
                        "cat(mean(wt$relevance))"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if mean_proc.returncode != 0:
                raise AssertionError(mean_proc.stderr)
            bundle_base_preds[bundle] = float(mean_proc.stdout.strip())

        # Each bundle must have a distinct mean relevance (different datasets)
        distinct_means = {round(v, 9) for v in bundle_base_preds.values()}
        assert len(distinct_means) == len(BUNDLES), (
            f"each bundle must have a distinct mean staged relevance; "
            f"got {bundle_base_preds}"
        )

        for bundle in BUNDLES:
            for tag in TAGS:
                fold_order = _profile_field(tag, "fold_order")
                rows = _rows_in_fold_order(_residual_rows(rep, bundle, tag), fold_order)
                reported_mono_band = float(rep["bundles"][bundle][tag]["mono_band"])
                expected_band_eps = float(_profile_field(tag, "band_eps"))
                assert abs(reported_mono_band - expected_band_eps) <= 1e-9, (
                    f"{bundle}/{tag} mono_band={reported_mono_band} must equal "
                    f"band_eps={expected_band_eps} from profile"
                )

                base_pred = float(rows[0]["score"]) - float(rows[0]["residual"])
                scores = [float(row["score"]) for row in rows]
                assert base_pred > 0, f"{bundle}/{tag} base_pred must come from staged relevance"
                assert abs(base_pred - bundle_base_preds[bundle]) <= 1e-9, (
                    f"{bundle}/{tag} base_pred={base_pred} does not match "
                    f"bundle mean relevance={bundle_base_preds[bundle]}"
                )

                for i in range(len(scores) - 1):
                    diff = scores[i + 1] - scores[i]
                    assert diff >= 1e-9, (
                        f"{bundle}/{tag} scores[{i+1}]={scores[i+1]} must exceed "
                        f"scores[{i}]={scores[i]} by >= 1e-9; diff={diff}"
                    )

                _assert_score_variation(scores, f"{bundle}/{tag} fold scores must vary")
                assert [row["fold"] for row in rows] == fold_order, (
                    f"{bundle}/{tag} fold sequence does not match profile fold_order"
                )
                for row in rows:
                    assert abs(float(row["residual"]) - (float(row["score"]) - base_pred)) <= 1e-9

    def test_cta06_grid_row(self) -> None:
        """strict_mono and relaxed_fast must diverge in fold order, band_eps, chain_hex, and
        witness scores across ALL bundles; all six chain_hex digests must be pairwise distinct;
        within each tag, scores across bundles must differ (different base_preds produce
        different score sets)."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        strict_order = _profile_field("strict_mono", "fold_order")
        fast_order = _profile_field("relaxed_fast", "fold_order")
        assert strict_order != fast_order, "profiles must use distinct fold orders"
        assert float(_profile_field("strict_mono", "band_eps")) != float(
            _profile_field("relaxed_fast", "band_eps")
        ), "profiles must use distinct band_eps values"

        # All six hex digests must be globally pairwise unique
        all_hexes: list[str] = []
        for bundle in BUNDLES:
            for tag in TAGS:
                h = rep["bundles"][bundle][tag]["chain_hex"]
                _assert_lowercase_hex(h)
                assert h not in all_hexes, (
                    f"chain_hex for {bundle}/{tag} duplicates another bundle/tag hex"
                )
                all_hexes.append(h)
        assert len(set(all_hexes)) == len(BUNDLES) * len(TAGS)

        for bundle in BUNDLES:
            strict_hex = rep["bundles"][bundle]["strict_mono"]["chain_hex"]
            fast_hex = rep["bundles"][bundle]["relaxed_fast"]["chain_hex"]
            assert strict_hex != fast_hex, f"{bundle}: tags must diverge in replay digest"

            strict_rows = _rows_in_fold_order(
                _residual_rows(rep, bundle, "strict_mono"), strict_order
            )
            fast_rows = _rows_in_fold_order(
                _residual_rows(rep, bundle, "relaxed_fast"), fast_order
            )
            strict_scores = [float(row["score"]) for row in strict_rows]
            fast_scores = [float(row["score"]) for row in fast_rows]
            assert strict_scores != fast_scores, f"{bundle} scores must differ across profiles"
            assert {round(s, 9) for s in strict_scores} != {round(s, 9) for s in fast_scores}, (
                f"{bundle} score sets must differ across profiles"
            )

        # Within each tag, scores must differ across bundles (different base_preds)
        for tag in TAGS:
            tag_order = _profile_field(tag, "fold_order")
            per_bundle_scores = {}
            for bundle in BUNDLES:
                rows = _rows_in_fold_order(_residual_rows(rep, bundle, tag), tag_order)
                per_bundle_scores[bundle] = tuple(round(float(r["score"]), 9) for r in rows)
            all_score_tuples = list(per_bundle_scores.values())
            assert len(set(all_score_tuples)) == len(BUNDLES), (
                f"{tag}: all bundles must produce distinct score tuples "
                f"(different base_preds from different datasets)"
            )

    def test_cta07_chain_hex(self) -> None:
        """chain_hex must match rebuilt replay bytes; RLCR magic must be present; epoch-exact
        ledger size must equal 2x single-epoch; second epoch bytes must be identical to first
        (same witness table, same encoding) — confirming APPEND not overwrite semantics."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()
        ledger_sizes: set[int] = set()

        for bundle in BUNDLES:
            for tag in TAGS:
                reported = rep["bundles"][bundle][tag]["chain_hex"]
                _assert_lowercase_hex(reported)

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
                assert reported == rebuilt, f"{bundle}/{tag}: reported chain_hex != rebuilt"

                cache_path = Path(f"/app/output/.chain_cache_{bundle}_{tag}.bin")
                assert cache_path.is_file(), f"missing cache ledger for {bundle}/{tag}"
                file_bytes = cache_path.stat().st_size
                assert file_bytes * 2 == len(reported)
                ledger_sizes.add(file_bytes)

                raw_bytes = cache_path.read_bytes()
                assert raw_bytes[:4] == b"RLCR", (
                    f"{bundle}/{tag} cache ledger must begin with RLCR magic"
                )

                fold_count = len(_profile_field(tag, "fold_order"))
                single_epoch_size = 8 + fold_count * 19
                assert file_bytes == single_epoch_size * 2, (
                    f"{bundle}/{tag} ledger size {file_bytes} must equal "
                    f"2 x {single_epoch_size} = {single_epoch_size * 2}"
                )

                # The second epoch must be byte-identical to the first epoch
                # (drive_suite runs the same witness table twice: refresh=TRUE then refresh=FALSE)
                # This confirms APPEND semantics (not overwrite) and deterministic encoding.
                epoch1 = raw_bytes[:single_epoch_size]
                epoch2 = raw_bytes[single_epoch_size:]
                assert epoch1 == epoch2, (
                    f"{bundle}/{tag} epoch1 and epoch2 in the cache ledger must be "
                    "byte-identical: drive_suite appends the same witness twice"
                )

        assert len(ledger_sizes) == 1, (
            "all bundle/tag cache ledgers must encode the same number of bytes"
        )

    def test_cta08_fold_agree(self) -> None:
        """Training witness rows and certificate replay must agree on all folds; residual
        arithmetic must be exact; inspect_mono.sh must return TRUE; m1_tables.rds witness_tbl
        scores must be monotonic; the fold bytes in the raw ledger header must match the
        fold_byte encoding (alpha=1, beta=2, gamma=3)."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = _load_report()

        # Fold byte encoding from scope_rules.md (alpha=1, beta=2, gamma=3)
        fold_byte_map = {"alpha": 1, "beta": 2, "gamma": 3}

        for bundle in BUNDLES:
            for tag in TAGS:
                fold_order = _profile_field(tag, "fold_order")
                rows = _rows_in_fold_order(_residual_rows(rep, bundle, tag), fold_order)
                assert len(rows) == len(fold_order)
                assert {row["fold"] for row in rows} == set(fold_order)

                base_pred = float(rows[0]["score"]) - float(rows[0]["residual"])
                scores = [float(row["score"]) for row in rows]
                for row in rows:
                    assert abs(float(row["residual"]) - (float(row["score"]) - base_pred)) <= 1e-9

                _assert_non_decreasing_scores(scores)
                _assert_score_variation(scores, f"{bundle}/{tag} witness scores must vary")

                proc_r = subprocess.run(
                    ["bash", "/app/environment/scripts/inspect_mono.sh", bundle, tag],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if proc_r.returncode != 0:
                    raise AssertionError(proc_r.stderr)
                assert proc_r.stdout.strip() == "TRUE", (
                    f"{bundle}/{tag} inspect_mono.sh must return TRUE"
                )

                # Verify fold bytes in the raw ledger match the documented encoding
                cache_path = Path(f"/app/output/.chain_cache_{bundle}_{tag}.bin")
                raw_bytes = cache_path.read_bytes()
                fold_count = len(fold_order)
                # single_epoch_size used for epoch slice verification below
                single_epoch_bytes = 8 + fold_count * 19
                # Parse epoch 1: skip 8-byte header, then read fold rows
                offset = 8  # skip RLCR magic + 4-byte count word
                for i, fold_name in enumerate(fold_order):
                    row_fold_byte = raw_bytes[offset + 2]  # bytes: bundle, tag, fold, score(8), residual(8)
                    expected_fold_byte = fold_byte_map[fold_name]
                    assert row_fold_byte == expected_fold_byte, (
                        f"{bundle}/{tag} epoch1 fold {i} byte={row_fold_byte} "
                        f"!= expected {expected_fold_byte} for fold '{fold_name}'"
                    )
                    offset += 19  # 1+1+1+8+8
                _ = single_epoch_bytes  # referenced in epoch identity check

                # Also verify from m1_tables.rds
                rds_proc = subprocess.run(
                    [
                        "Rscript",
                        "-e",
                        (
                            "source('/app/environment/lib/common_io.R'); "
                            f"m1<-readRDS('/app/output/m1_tables.rds'); "
                            f"wt<-m1$witness_tbls$bundle_{bundle}_{tag}; "
                            "if (is.null(wt)) stop('witness table missing'); "
                            f"prof<-read_profile('/app/environment/profiles/{tag}.toml'); "
                            "ord<-match(wt$fold, prof$fold_order); "
                            "wt2<-wt[order(ord),]; "
                            "cat(all(diff(wt2$score) >= 1e-9))"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if rds_proc.returncode != 0:
                    raise AssertionError(rds_proc.stderr)
                assert rds_proc.stdout.strip() == "TRUE", (
                    f"{bundle}/{tag} m1_tables.rds witness_tbl scores must be monotonic"
                )

    def test_cta09_repeat_guard(self) -> None:
        """Cache wipe must remove all artifacts; scope checker must fail; after restore,
        chain_hex values must be byte-for-byte identical to pre-wipe; monotonicity must hold;
        the ledger must not gain or lose bytes during the backup-wipe-restore cycle."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"

        pre_wipe_rep = _load_report()
        pre_wipe_hexes = {
            (b, t): pre_wipe_rep["bundles"][b][t]["chain_hex"]
            for b in BUNDLES for t in TAGS
        }
        # Also record pre-wipe ledger sizes
        pre_wipe_sizes = {
            (b, t): Path(f"/app/output/.chain_cache_{b}_{t}.bin").stat().st_size
            for b in BUNDLES for t in TAGS
        }

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
        finally:
            _restore_outputs()
            _cleanup_backup()

        assert REPORT.is_file(), "report must be restored"
        post_restore_rep = _load_report()
        for b in BUNDLES:
            for t in TAGS:
                post_hex = post_restore_rep["bundles"][b][t]["chain_hex"]
                assert post_hex == pre_wipe_hexes[(b, t)], (
                    f"{b}/{t}: restored chain_hex differs from original"
                )
                # Ledger file size must also be unchanged after restore
                post_size = Path(f"/app/output/.chain_cache_{b}_{t}.bin").stat().st_size
                assert post_size == pre_wipe_sizes[(b, t)], (
                    f"{b}/{t}: restored ledger size {post_size} != pre-wipe {pre_wipe_sizes[(b, t)]}"
                )

        for bundle in BUNDLES:
            for tag in TAGS:
                fold_order = _profile_field(tag, "fold_order")
                rows = _rows_in_fold_order(
                    _residual_rows(post_restore_rep, bundle, tag), fold_order
                )
                _assert_non_decreasing_scores([float(row["score"]) for row in rows])

    def test_cta10_q4_trap(self) -> None:
        """Interim snap tallies alone must not satisfy terminal grading; snap structure must
        be valid; band values must be distinct and positive; fake report with correct structure
        but absent pipeline tables must still fail the checker; the checker must also fail
        if only m1_tables.rds exists without m2_witness.rds or cache ledgers."""
        snap = json.loads(INTERIM.read_text())
        assert snap.get("headline_ok") is True
        assert snap.get("bundle") == "w3"
        assert snap.get("residual_rows"), "interim snap must carry historical adjustment bands"
        assert "chain_hint" in snap
        assert isinstance(snap["residual_rows"], list)
        for entry in snap["residual_rows"]:
            assert "row_ix" in entry and "band" in entry
            assert float(entry["band"]) > 0
        bands = [float(e["band"]) for e in snap["residual_rows"]]
        assert len(set(bands)) == len(bands), "snap band values must be distinct per row_ix"

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
            assert not M1.is_file()
            assert not Path("/app/output/m2_witness.rds").is_file()

            # Fake report with correct JSON structure must still fail
            fake_report_path = Path("/app/output/residual_scope.json")
            fake_report_path.write_text(
                json.dumps({"bundles": {"w3": {}, "w4": {}, "k5": {}}})
            )
            rechk = _run_scope_chk()
            assert rechk.returncode != 0, (
                "checker must fail with fake report when pipeline tables absent"
            )
            fake_report_path.unlink(missing_ok=True)

            # Partial state: m1_tables.rds alone (no m2_witness.rds, no cache) must also fail
            shutil.copy2(
                Path("/app/output") / "m1_tables.rds.bak",
                M1,
            )
            partial_chk = _run_scope_chk()
            assert partial_chk.returncode != 0, (
                "checker must fail with only m1_tables.rds present and no witness or cache ledgers"
            )
            M1.unlink(missing_ok=True)
        finally:
            _restore_outputs()
            _cleanup_backup()

    def test_cta11_clean_rebuild(self) -> None:
        """Pipeline must regenerate valid outputs from scratch after a cache wipe; rebuilt
        chain_hex must be deterministic (match pre-wipe); ledger must reflect two epochs with
        RLCR magic; the two epochs in the rebuilt ledger must be byte-identical confirming
        APPEND semantics; full-grid monotonicity and score variation must hold."""
        _backup_outputs()
        pre_hexes: dict[tuple[str, str], str] = {}
        if REPORT.is_file():
            pre_rep = _load_report()
            for b in BUNDLES:
                for t in TAGS:
                    pre_hexes[(b, t)] = pre_rep["bundles"][b][t]["chain_hex"]

        try:
            subprocess.run(
                ["bash", "/app/environment/migrations/cln4.sh"],
                check=True, timeout=60,
            )
            subprocess.run(
                ["bash", "/app/environment/scripts/stage_tables.sh"],
                check=True, timeout=120,
            )
            subprocess.run(
                ["bash", "/app/environment/scripts/drive_suite.sh"],
                check=True, timeout=120,
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
                    assert cache_path.is_file()
                    reported = rep["bundles"][bundle][tag]["chain_hex"]
                    _assert_lowercase_hex(reported)

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

                    if (bundle, tag) in pre_hexes:
                        assert reported == pre_hexes[(bundle, tag)], (
                            f"{bundle}/{tag}: rebuilt chain_hex differs from pre-wipe; "
                            "pipeline must be deterministic"
                        )

                    fold_count = len(_profile_field(tag, "fold_order"))
                    single_epoch_size = 8 + fold_count * 19
                    file_bytes = cache_path.stat().st_size
                    assert file_bytes == single_epoch_size * 2

                    raw_bytes = cache_path.read_bytes()
                    assert raw_bytes[:4] == b"RLCR"

                    # Epoch1 must be byte-identical to epoch2 (APPEND not overwrite)
                    epoch1 = raw_bytes[:single_epoch_size]
                    epoch2 = raw_bytes[single_epoch_size:]
                    assert epoch1 == epoch2, (
                        f"{bundle}/{tag} rebuilt ledger epoch1 != epoch2; "
                        "drive_suite must append identical epochs, not overwrite"
                    )

            for bundle in BUNDLES:
                for tag in TAGS:
                    fold_order = _profile_field(tag, "fold_order")
                    rows = _rows_in_fold_order(_residual_rows(rep, bundle, tag), fold_order)
                    scores = [float(row["score"]) for row in rows]
                    _assert_non_decreasing_scores(scores)
                    _assert_score_variation(scores, f"{bundle}/{tag} rebuilt scores must vary")
        finally:
            _restore_outputs()
            _cleanup_backup()
