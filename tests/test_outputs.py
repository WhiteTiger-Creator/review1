import json
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

    def test_cta04_bounds_row(self) -> None:
        """Witness residual magnitudes must stay inside public tolerance classes."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = json.loads(REPORT.read_text())
        for bundle in ("w3", "w4", "k5"):
            for tag in ("strict_mono", "relaxed_fast"):
                rows = rep["bundles"][bundle][tag]["residual_rows"]
                floor_v = 0.05
                eps = 0.001 if tag == "strict_mono" else 0.002
                for row in rows:
                    assert abs(float(row["residual"])) <= floor_v + eps + 1e-9

    def test_cta05_band_row(self) -> None:
        """Monotonic score ordering must hold on training folds per active profile."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = json.loads(REPORT.read_text())
        for bundle in ("w3", "w4", "k5"):
            for tag in ("strict_mono", "relaxed_fast"):
                band = float(rep["bundles"][bundle][tag]["mono_band"])
                profile = (ENV / "profiles" / f"{tag}.toml").read_text()
                for line in profile.splitlines():
                    if line.startswith("band_eps"):
                        expected = float(line.split("=", 1)[1].strip())
                        break
                else:
                    raise AssertionError(f"missing band_eps in {tag}")
                assert abs(band - expected) <= 1e-9

    def test_cta06_grid_row(self) -> None:
        """strict_mono and relaxed_fast suite semantics must differ as documented."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = json.loads(REPORT.read_text())
        w3_strict = rep["bundles"]["w3"]["strict_mono"]["chain_hex"]
        w3_fast = rep["bundles"]["w3"]["relaxed_fast"]["chain_hex"]
        assert w3_strict != w3_fast

        def _fold_order(name: str) -> list[str]:
            text = (ENV / "profiles" / f"{name}.toml").read_text()
            for line in text.splitlines():
                if line.startswith("fold_order"):
                    inner = line.split("=", 1)[1].strip()
                    return [x.strip().strip('"') for x in inner.strip("[]").split(",")]
            raise AssertionError(f"missing fold_order in {name}")

        assert _fold_order("strict_mono") != _fold_order("relaxed_fast")

    def test_cta07_chain_hex(self) -> None:
        """chain_hex must match sha256 over rebuilt replay bytes for each bundle and tag."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = json.loads(REPORT.read_text())
        for bundle in ("w3", "w4", "k5"):
            for tag in ("strict_mono", "relaxed_fast"):
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

    def test_cta08_fold_agree(self) -> None:
        """Training witness rows and certificate replay must agree on holdout folds."""
        assert REPORT.is_file(), "terminal report missing from pipeline output"
        rep = json.loads(REPORT.read_text())
        for bundle in ("w3", "w4", "k5"):
            for tag in ("strict_mono", "relaxed_fast"):
                rows = rep["bundles"][bundle][tag]["residual_rows"]
                assert len(rows) == 3
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
            fail_proc = subprocess.run(
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
            if fail_proc.returncode == 0:
                raise AssertionError("expected checker failure after cache wipe")
        finally:
            _restore_outputs()
            _cleanup_backup()

    def test_cta10_q4_trap(self) -> None:
        """Interim snap tallies alone must not satisfy terminal grading."""
        snap = json.loads(INTERIM.read_text())
        assert snap.get("headline_ok") is True
        _backup_outputs()
        try:
            for name in OUTPUT_ARTIFACTS:
                artifact = Path("/app/output") / name
                if artifact.exists():
                    artifact.unlink()
            fail_proc = subprocess.run(
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
            if fail_proc.returncode == 0:
                raise AssertionError("expected checker failure without pipeline output")
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
            proc = subprocess.run(
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
                check=False,
                timeout=90,
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, proc.stderr
        finally:
            _restore_outputs()
            _cleanup_backup()
