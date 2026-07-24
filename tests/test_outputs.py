"""Independent behavioral verifier for adaptive HDF5 checkpoint restart."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import h5py
import numpy as np
import pytest

ROOT = Path("/app/environment")
BIN = ROOT / "bin" / "x7_orch"
BUILD_SH = ROOT / "scripts" / "build_x7.sh"
ENTRY = ROOT / "h1" / "run_x7.sh"
GATE = ROOT / "tools" / "x7_gate"
RECORD = Path("/app/output/run-record.json")
FINAL = Path("/app/output/final.h5")
STAGE = Path("/app/output/stage")
CONTRACT = ROOT / "docs" / "restart_contract.md"
MASS_RTOL = 1e-12


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _digest(vals: list[float]) -> str:
    payload = b"".join(struct.pack("<d", float(v)) for v in vals)
    return hashlib.sha256(payload).hexdigest()


def _cfg(tag: str) -> dict:
    return json.loads((ROOT / "cfg_store" / f"cfg_{tag}.json").read_text())


def _field_cksum(vals: list[float]) -> float:
    return sum(v * (1.0 + 1.0e-6 * i) for i, v in enumerate(vals))


def _mpirun(np: int, *args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [
        "mpirun",
        "--allow-run-as-root",
        "--oversubscribe",
        "-np",
        str(np),
        str(BIN),
        *args,
    ]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=merged, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"mpirun failed rc={proc.returncode}\ncmd={' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def _read_final(path: Path, n_global: int) -> tuple[list[float], list[float], list[float], dict]:
    assert path.is_file(), f"missing final {path}"
    with h5py.File(path, "r") as f:
        owned = [float(x) for x in f["owned"][...]]
        assert len(owned) == n_global
        assert any(abs(v) > 0 for v in owned)
        dt = [float(x) for x in f["hist"]["dt_seq"][...]]
        mass = [float(x) for x in f["hist"]["mass_seq"][...]]
        ctrl = {}
        if "ctrl" in f:
            c = f["ctrl"]
            ctrl = {
                "last_dt": float(c.attrs.get("last_dt", 0.0)),
                "n_reject": int(c.attrs.get("n_reject", 0)),
                "n_accept": int(c.attrs.get("n_accept", 0)),
                "accum": float(c.attrs.get("accum", 0.0)),
            }
        return owned, dt, mass, ctrl


def _mass_equiv(a: list[float], b: list[float]) -> None:
    assert len(a) == len(b) and a and b
    for i, (x, y) in enumerate(zip(a, b)):
        scale = max(abs(x), abs(y), 1e-30)
        assert abs(x - y) / scale <= MASS_RTOL, f"mass[{i}] {x} vs {y}"


def _ctrl_equiv(a: dict, b: dict) -> None:
    assert a and b
    assert a["n_accept"] == b["n_accept"]
    assert a["n_reject"] == b["n_reject"]
    assert abs(a["last_dt"] - b["last_dt"]) <= 1e-15
    assert abs(a["accum"] - b["accum"]) <= 1e-12


def _traj_match(un: Path, co: Path, n_global: int) -> None:
    uo, udt, um, uc = _read_final(un, n_global)
    co_, cdt, cm, cc = _read_final(co, n_global)
    assert _digest(uo) == _digest(co_)
    assert udt == cdt
    _mass_equiv(um, cm)
    _ctrl_equiv(uc, cc)


def _write_continuous(workdir: Path, cfg_tag: str, prof: str, np: int, write_ckpt: bool) -> Path:
    cfg = ROOT / "cfg_store" / f"cfg_{cfg_tag}.json"
    penv = ROOT / "profiles" / f"{prof}.prof"
    stage = workdir / f"cont_{np}"
    stage.mkdir(parents=True, exist_ok=True)
    final = stage / "final.h5"
    ckpt = workdir / "ckpt.h5"
    args = [
        "--mode",
        "continuous",
        "--cfg",
        str(cfg),
        "--profile",
        str(penv),
        "--stage",
        str(stage),
        "--final",
        str(final),
    ]
    if write_ckpt:
        args += ["--write-ckpt", str(ckpt)]
    _mpirun(np, *args)
    return ckpt if write_ckpt else final


def _continue_run(
    workdir: Path,
    cfg_tag: str,
    prof: str,
    np: int,
    ckpt: Path,
    check: bool = True,
) -> subprocess.CompletedProcess:
    cfg = ROOT / "cfg_store" / f"cfg_{cfg_tag}.json"
    penv = ROOT / "profiles" / f"{prof}.prof"
    stage = workdir / f"continue_{np}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    final = stage / "final.h5"
    return _mpirun(
        np,
        "--mode",
        "continue",
        "--cfg",
        str(cfg),
        "--profile",
        str(penv),
        "--ckpt",
        str(ckpt),
        "--stage",
        str(stage),
        "--final",
        str(final),
        check=check,
    )


def _clone_gen(f: h5py.File, src_name: str, dst_id: int) -> h5py.Group:
    src = f[src_name]
    name = f"gen_{dst_id:04d}"
    if name in f:
        del f[name]
    dst = f.create_group(name)
    for k, v in src.attrs.items():
        dst.attrs[k] = v
    dst.attrs["gen_id"] = dst_id
    for key in src:
        src.copy(key, dst, name=key)
    return dst


def _primary_gen(f: h5py.File) -> str:
    keys = sorted(k for k in f if k.startswith("gen_"))
    assert keys, "no generation groups"
    return keys[0]


@pytest.fixture(scope="session")
def rebuilt_binary() -> Path:
    """Clean rebuild from the agent-editable source tree before behavioral tests."""
    build_dir = ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if BIN.exists():
        BIN.unlink()
    subprocess.run(["bash", str(BUILD_SH)], check=True)
    assert BIN.is_file(), "x7_orch missing after rebuild"
    return BIN


def test_newest_recoverable_generation_is_selected(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Newer incomplete/inconsistent committed-looking gens must fall back to newest recoverable."""
    ckpt = _write_continuous(tmp_path, "sa", "px", 2, write_ckpt=True)
    with h5py.File(ckpt, "a") as f:
        src = _primary_gen(f)
        # Incomplete (missing ranks) but committed=1
        g2 = _clone_gen(f, src, 2)
        g2.attrs["committed"] = 1
        for name in list(g2):
            if name.startswith("r1_"):
                del g2[name]
        # Duplicate/missing GID coverage, committed=1
        g3 = _clone_gen(f, src, 3)
        g3.attrs["committed"] = 1
        gids = g3["r0_gids"][...]
        if len(gids) > 1:
            gids[1] = gids[0]
            g3["r0_gids"][...] = gids
        # Checksum mismatch
        g4 = _clone_gen(f, src, 4)
        g4.attrs["committed"] = 1
        g4.attrs["field_cksum"] = float(g4.attrs.get("field_cksum", 0.0)) + 123.456
        # Inconsistent history length
        g5 = _clone_gen(f, src, 5)
        g5.attrs["committed"] = 1
        if "hist" in g5 and "dt_seq" in g5["hist"]:
            dt = list(g5["hist"]["dt_seq"][...])
            if dt:
                del g5["hist"]["dt_seq"]
                g5["hist"].create_dataset("dt_seq", data=np.asarray(dt[:-1], dtype=np.float64))

    before = _sha(ckpt)
    proc = _continue_run(tmp_path, "sa", "px", 5, ckpt)
    assert proc.returncode == 0
    assert _sha(ckpt) == before
    picked = json.loads((tmp_path / "continue_5" / "picked.json").read_text())
    assert picked["gen_id"] == 1


def test_generation_history_and_controller_are_snapshot_local(
    rebuilt_binary: Path, tmp_path: Path
) -> None:
    """A generation must not borrow history/controller state from a sibling generation."""
    ckpt = _write_continuous(tmp_path, "sb", "px", 2, write_ckpt=True)
    cfg = _cfg("sb")
    with h5py.File(ckpt, "a") as f:
        src = _primary_gen(f)
        g2 = _clone_gen(f, src, 2)
        g2.attrs["committed"] = 1
        # Keep generation step at the field snapshot, but attach a longer alien history
        # and mismatched controller counters so recoverability must reject the borrow.
        step = int(g2.attrs.get("step", cfg["ckpt_step"]))
        if "hist" in g2:
            del g2["hist"]
        hg = g2.create_group("hist")
        alien_dt = np.linspace(1e-4, 2e-4, step + 3)
        alien_m = np.ones_like(alien_dt)
        hg.create_dataset("dt_seq", data=alien_dt)
        hg.create_dataset("mass_seq", data=alien_m)
        hg.attrs["step"] = int(alien_dt.size)
        if "ctrl" in g2:
            del g2["ctrl"]
        cg = g2.create_group("ctrl")
        cg.attrs["last_dt"] = 9.9e-3
        cg.attrs["n_reject"] = 99
        cg.attrs["n_accept"] = int(alien_dt.size)
        cg.attrs["accum"] = 42.0
        g2.attrs["step"] = step

    _continue_run(tmp_path, "sb", "px", 3, ckpt)
    picked = json.loads((tmp_path / "continue_3" / "picked.json").read_text())
    assert picked["gen_id"] == 1
    _, dt, _, ctrl = _read_final(tmp_path / "continue_3" / "final.h5", int(cfg["n_global"]))
    assert 9.9e-3 not in dt
    assert ctrl["n_reject"] != 99


def test_shuffled_gid_reconstruction_excludes_halos(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Shuffled owned GIDs with poisoned halos must rebuild the exact canonical field."""
    ckpt = _write_continuous(tmp_path, "sa", "px", 2, write_ckpt=True)
    cfg = _cfg("sa")
    with h5py.File(ckpt, "a") as f:
        g = f[_primary_gen(f)]
        nproc = int(g.attrs["nproc_write"])
        for r in range(nproc):
            owned = g[f"r{r}_owned"][...]
            gids = g[f"r{r}_gids"][...]
            order = np.arange(len(gids))[::-1]
            g[f"r{r}_owned"][...] = owned[order]
            g[f"r{r}_gids"][...] = gids[order]
            g[f"r{r}_ghost_lo"][...] = np.asarray([1.0e9], dtype=np.float64)
            g[f"r{r}_ghost_hi"][...] = np.asarray([owned[0] if len(owned) else 0.0], dtype=np.float64)
        # Recompute checksum for still-valid generation after shuffle
        global_vals = np.zeros(int(cfg["n_global"]), dtype=np.float64)
        for r in range(nproc):
            owned = g[f"r{r}_owned"][...]
            gids = g[f"r{r}_gids"][...]
            for v, gid in zip(owned, gids):
                global_vals[int(gid)] = float(v)
        g.attrs["field_cksum"] = _field_cksum(global_vals.tolist())

    un = _write_continuous(tmp_path / "un", "sa", "px", 5, write_ckpt=False)
    _continue_run(tmp_path, "sa", "px", 5, ckpt)
    _traj_match(un, tmp_path / "continue_5" / "final.h5", int(cfg["n_global"]))


def test_duplicate_or_missing_gid_generation_is_rejected(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Committed generation with duplicate+missing GID coverage must be rejected."""
    ckpt = _write_continuous(tmp_path, "sc", "qy", 3, write_ckpt=True)
    with h5py.File(ckpt, "a") as f:
        src = _primary_gen(f)
        g2 = _clone_gen(f, src, 2)
        g2.attrs["committed"] = 1
        gids = g2["r0_gids"][...]
        if len(gids) > 1:
            gids[0] = gids[1]
            g2["r0_gids"][...] = gids
    _continue_run(tmp_path, "sc", "qy", 4, ckpt)
    picked = json.loads((tmp_path / "continue_4" / "picked.json").read_text())
    assert picked["gen_id"] == 1


def test_two_to_five_repartition_matches_uninterrupted(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Uneven 2→5 repartition must match uninterrupted scientific trajectory."""
    cfg = _cfg("sa")
    un = _write_continuous(tmp_path / "un", "sa", "px", 5, write_ckpt=False)
    ckpt = _write_continuous(tmp_path / "wr", "sa", "px", 2, write_ckpt=True)
    _continue_run(tmp_path / "co", "sa", "px", 5, ckpt)
    _traj_match(un, tmp_path / "co" / "continue_5" / "final.h5", int(cfg["n_global"]))


def test_five_to_three_repartition_matches_uninterrupted(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Uneven 5→3 repartition must match uninterrupted scientific trajectory."""
    cfg = _cfg("sb")
    un = _write_continuous(tmp_path / "un", "sb", "qy", 3, write_ckpt=False)
    ckpt = _write_continuous(tmp_path / "wr", "sb", "qy", 5, write_ckpt=True)
    _continue_run(tmp_path / "co", "sb", "qy", 3, ckpt)
    _traj_match(un, tmp_path / "co" / "continue_3" / "final.h5", int(cfg["n_global"]))


def test_legacy_and_current_layouts_remain_supported(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Legacy root layout and current grouped layout must both continue correctly."""
    cfg = _cfg("sa")
    un = _write_continuous(tmp_path / "un", "sa", "qy", 4, write_ckpt=False)
    ckpt = _write_continuous(tmp_path / "wr", "sa", "qy", 2, write_ckpt=True)

    legacy = tmp_path / "legacy.h5"
    with h5py.File(ckpt, "r") as s, h5py.File(legacy, "w") as d:
        g = s[_primary_gen(s)]
        d.attrs["layout"] = 1
        for k in ("gen_id", "step", "nproc_write", "committed"):
            d.attrs[k] = g.attrs[k]
        if "fingerprint" in g.attrs:
            d.attrs["fingerprint"] = g.attrs["fingerprint"]
        if "field_cksum" in g.attrs:
            d.attrs["field_cksum"] = g.attrs["field_cksum"]
        nproc = int(g.attrs["nproc_write"])
        for r in range(nproc):
            for suffix in ("owned", "ghost_lo", "ghost_hi", "gids"):
                d.create_dataset(f"{suffix}_r{r}", data=g[f"r{r}_{suffix}"][...])
        hist_src = g["hist"] if "hist" in g else s["hist"]
        hg = d.create_group("hist")
        hg.create_dataset("dt_seq", data=hist_src["dt_seq"][...])
        hg.create_dataset("mass_seq", data=hist_src["mass_seq"][...])
        hg.attrs["step"] = int(hist_src.attrs.get("step", g.attrs["step"]))
        ctrl_src = g["ctrl"] if "ctrl" in g else s.get("ctrl")
        if ctrl_src is not None:
            for k in ("last_dt", "n_reject", "n_accept", "accum"):
                d.attrs[f"ctrl_{k}"] = ctrl_src.attrs[k]

    _continue_run(tmp_path / "leg", "sa", "qy", 4, legacy)
    _continue_run(tmp_path / "grp", "sa", "qy", 4, ckpt)
    _traj_match(un, tmp_path / "leg" / "continue_4" / "final.h5", int(cfg["n_global"]))
    _traj_match(un, tmp_path / "grp" / "continue_4" / "final.h5", int(cfg["n_global"]))


def test_profile_mismatch_fails_without_output(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Incompatible profile fingerprint must fail and leave no final artifact."""
    ckpt = _write_continuous(tmp_path / "wr", "sa", "px", 2, write_ckpt=True)
    stage = tmp_path / "bad"
    stage.mkdir()
    final = stage / "final.h5"
    proc = _mpirun(
        3,
        "--mode",
        "continue",
        "--cfg",
        str(ROOT / "cfg_store" / "cfg_sa.json"),
        "--profile",
        str(ROOT / "profiles" / "qy.prof"),
        "--ckpt",
        str(ckpt),
        "--stage",
        str(stage),
        "--final",
        str(final),
        check=False,
    )
    assert proc.returncode != 0
    assert not final.exists()


def test_crash_during_publish_leaves_no_final(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Deterministic publish failpoint must leave no final.h5 artifact."""
    stage = tmp_path / "fp"
    stage.mkdir()
    final = stage / "final.h5"
    proc = _mpirun(
        2,
        "--mode",
        "continuous",
        "--cfg",
        str(ROOT / "cfg_store" / "cfg_sa.json"),
        "--profile",
        str(ROOT / "profiles" / "px.prof"),
        "--stage",
        str(stage),
        "--final",
        str(final),
        env={"X7_FAILPOINT": "before_publish_rename"},
        check=False,
    )
    assert proc.returncode != 0
    assert not final.exists()


def test_repeated_continuation_is_idempotent(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Repeating the same continuation must preserve field, history, controller, and output bytes."""
    cfg = _cfg("sb")
    ckpt = _write_continuous(tmp_path / "wr", "sb", "px", 2, write_ckpt=True)
    h0 = _sha(ckpt)
    _continue_run(tmp_path / "c1", "sb", "px", 5, ckpt)
    f1 = tmp_path / "c1" / "continue_5" / "final.h5"
    o1, d1, m1, c1 = _read_final(f1, int(cfg["n_global"]))
    assert _sha(ckpt) == h0
    _continue_run(tmp_path / "c2", "sb", "px", 5, ckpt)
    f2 = tmp_path / "c2" / "continue_5" / "final.h5"
    o2, d2, m2, c2 = _read_final(f2, int(cfg["n_global"]))
    assert _digest(o1) == _digest(o2)
    assert d1 == d2
    _mass_equiv(m1, m2)
    _ctrl_equiv(c1, c2)
    assert _sha(ckpt) == h0


def test_checkpoint_bytes_are_never_modified(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Successful and failed continuation must leave supplied checkpoint bytes unchanged."""
    ckpt = _write_continuous(tmp_path / "wr", "sc", "qy", 2, write_ckpt=True)
    h0 = _sha(ckpt)
    _continue_run(tmp_path / "ok", "sc", "qy", 4, ckpt)
    assert _sha(ckpt) == h0
    _mpirun(
        3,
        "--mode",
        "continue",
        "--cfg",
        str(ROOT / "cfg_store" / "cfg_sc.json"),
        "--profile",
        str(ROOT / "profiles" / "px.prof"),
        "--ckpt",
        str(ckpt),
        "--stage",
        str(tmp_path / "bad"),
        "--final",
        str(tmp_path / "bad" / "final.h5"),
        check=False,
    )
    assert _sha(ckpt) == h0


def test_fresh_run_behavior_is_preserved(rebuilt_binary: Path, tmp_path: Path) -> None:
    """Repair must not break clean uninterrupted continuous runs."""
    cfg = _cfg("sa")
    a = _write_continuous(tmp_path / "a", "sa", "px", 4, write_ckpt=False)
    b = _write_continuous(tmp_path / "b", "sa", "px", 4, write_ckpt=False)
    _traj_match(a, b, int(cfg["n_global"]))
    assert CONTRACT.is_file()


def test_run_record_matches_independent_observations(rebuilt_binary: Path) -> None:
    """Public matrix emitter rows must match direct HDF5 observations (emitter is not truth)."""
    # Keep matrix runtime bounded: run entry once for this session-scoped check.
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    if FINAL.exists():
        FINAL.unlink()
    if RECORD.exists():
        RECORD.unlink()
    subprocess.run(["bash", str(ENTRY)], check=True)
    assert RECORD.is_file() and FINAL.is_file()
    payload = json.loads(RECORD.read_text())
    cells = payload.get("cells")
    assert cells
    for cell in cells:
        scen = cell["scenario"]
        prof = cell["profile"]
        tr = cell["transition"]
        cell_dir = STAGE / f"{scen}_{prof}_{tr}"
        cfg = _cfg(scen)
        n = int(cfg["n_global"])
        un = cell_dir / "uninterrupted" / "final.h5"
        co = cell_dir / "continue" / "final.h5"
        uo, _, _, _ = _read_final(un, n)
        co_owned, cdt, cmass, cctrl = _read_final(co, n)
        assert cell["uninterrupted_digest"] == _digest(uo)
        assert cell["continued_digest"] == _digest(co_owned)
        assert cell["field_digest"] == _digest(co_owned)
        assert cell["timestep_seq"] == cdt
        _mass_equiv(cell["mass_history"], cmass)
        controller = cell.get("controller")
        if controller:
            _ctrl_equiv(controller, cctrl)
        assert cell["uninterrupted_digest"] == cell["continued_digest"]
        ckpt = cell_dir / "legacy.h5" if (cell_dir / "legacy.h5").is_file() else cell_dir / "ckpt.h5"
        assert cell["fixture_sha256"] == _sha(ckpt)
