"""Verifier for vault completion via live autoplay and engine replay."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

OUT = Path("/app/output/vault_state.json")
OUT_HOLDOUT = Path("/app/output/vault_state_holdout.json")
OUT_MIRROR = Path("/app/output/vault_state_mirror.json")
ENGINE = "/app/environment/dist/src/main.js"
AUTOPLAY_PATH = "/app/output/autoplay.js"
AUTOPLAY = Path(AUTOPLAY_PATH)
CHAIN = "ember_core,veil_latch,crest_key"
BUDGET = 220
SEED_OUT = {
    "nominal": OUT,
    "holdout": OUT_HOLDOUT,
    "mirror": OUT_MIRROR,
}
VALID_CMDS = {"move", "look", "take", "use", "attack", "exit"}


def _engine_bak() -> Path:
    return Path(ENGINE + ".bak")


def _hit_log() -> Path:
    return Path("/app/output") / "engine_hits.log"


def _seal(seed: str, floors_cleared: int, apex_stage: str, turns_used: int, used_chain: str) -> str:
    payload = f"{seed}|{floors_cleared}|{apex_stage}|{turns_used}|{used_chain}"
    script = (
        "const c=require('crypto');"
        "process.stdout.write(c.createHash('sha256').update(process.argv[1],'utf8').digest('hex'));"
    )
    digest = subprocess.check_output(["node", "-e", script, payload])
    return digest.decode("utf-8").strip()


def _trace_path(seed: str) -> Path:
    return Path("/app/output") / f"trace_{seed}.txt"


def _wipe_seed_artifacts(seed: str) -> None:
    out = SEED_OUT[seed]
    if out.exists():
        out.unlink()
    trace = _trace_path(seed)
    if trace.exists():
        trace.unlink()


def _assert_autoplay_surface() -> str:
    assert AUTOPLAY.is_file(), f"missing {AUTOPLAY_PATH}"
    assert not AUTOPLAY.is_symlink(), "autoplay.js must be a regular file"
    body = AUTOPLAY.read_text(encoding="utf-8")
    assert "--seed" in body and "--out" in body, "autoplay.js must document/accept --seed and --out"
    assert re.search(r"child_process|spawn\s*\(|execFile\s*\(|fork\s*\(", body), (
        "autoplay.js must drive the engine as a child process"
    )
    assert "exit_seal_digest" not in body
    assert re.search(r"floors_cleared\s*\"?\s*:\s*5", body) is None
    return body


def _install_engine_probe() -> None:
    real = Path(ENGINE)
    bak = _engine_bak()
    assert real.is_file(), f"missing engine at {ENGINE}"
    if not bak.exists():
        real.replace(bak)
    hit = json.dumps(str(_hit_log()))
    bak_js = json.dumps(str(bak))
    Path(ENGINE).write_text(
        "const { spawn } = require('child_process');\n"
        "const fs = require('fs');\n"
        f"fs.appendFileSync({hit}, 'hit\\n');\n"
        f"const child = spawn(process.execPath, [{bak_js}, ...process.argv.slice(2)], {{\n"
        "  stdio: ['inherit', 'inherit', 'inherit'],\n"
        "});\n"
        "child.on('exit', (code, signal) => {\n"
        "  if (signal) {\n"
        "    process.kill(process.pid, signal);\n"
        "    return;\n"
        "  }\n"
        "  process.exit(code === null ? 1 : code);\n"
        "});\n"
        "child.on('error', (err) => {\n"
        "  console.error(err);\n"
        "  process.exit(1);\n"
        "});\n",
        encoding="utf-8",
    )


def _restore_engine() -> None:
    bak = _engine_bak()
    real = Path(ENGINE)
    if bak.exists():
        if real.exists():
            real.unlink()
        bak.replace(real)


def _run_autoplay(seed: str, out: Path | None = None) -> None:
    target = out or SEED_OUT[seed]
    trace = _trace_path(seed)
    if target.exists():
        target.unlink()
    if trace.exists():
        trace.unlink()
    started = time.time_ns()
    hit_path = _hit_log()
    hit_before = hit_path.read_text(encoding="utf-8").count("hit") if hit_path.exists() else 0

    proc = subprocess.run(
        [
            "node",
            AUTOPLAY_PATH,
            "--seed",
            seed,
            "--out",
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        cwd="/app",
        env=os.environ.copy(),
    )
    assert proc.returncode == 0, (
        f"autoplay failed for seed={seed} rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert target.is_file(), f"autoplay did not write {target}"
    assert trace.is_file() and trace.stat().st_size > 0, f"autoplay did not write fresh {trace}"
    assert trace.stat().st_mtime_ns >= started - 2_000_000_000, f"stale transcript {trace}"

    lines = [ln.strip() for ln in trace.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, f"empty transcript {trace}"
    for ln in lines:
        cmd = ln.split()[0]
        assert cmd in VALID_CMDS, f"invalid transcript command {ln!r}"

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data.get("seed") == seed, f"autoplay out seed mismatch for {seed}"

    hit_after = hit_path.read_text(encoding="utf-8").count("hit") if hit_path.exists() else 0
    assert hit_after > hit_before, (
        f"autoplay for seed={seed} never invoked the vault engine child process"
    )


def _replay(seed: str, out: Path) -> dict:
    """Authoritative grading path: replay transcript through the real engine."""
    if out.exists():
        out.unlink()
    trace = _trace_path(seed)
    assert trace.is_file(), f"missing transcript {trace}"
    _restore_engine()
    proc = subprocess.run(
        ["node", ENGINE, "--seed", seed, "--out", str(out)],
        input=trace.read_text(encoding="utf-8"),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"engine replay failed for {seed}: {proc.stderr}"
    assert out.is_file(), f"replay did not write {out}"
    return json.loads(out.read_text(encoding="utf-8"))


def _assert_complete(data: dict, seed: str) -> None:
    assert data.get("seed") == seed
    assert data.get("floors_cleared") == 5
    assert int(data.get("open_flag_epoch", 0)) >= 1
    assert data.get("apex_stage") == "cleared"
    assert data.get("used_chain") == CHAIN
    assert int(data.get("turns_used", 9999)) <= BUDGET
    expected = _seal(
        seed,
        int(data["floors_cleared"]),
        str(data["apex_stage"]),
        int(data["turns_used"]),
        str(data["used_chain"]),
    )
    assert data.get("exit_seal_digest") == expected


@pytest.fixture(scope="module")
def live_clears():
    """Drive autoplay for every seed, then rebuild JSON via engine replay."""
    _assert_autoplay_surface()
    _hit_log().write_text("", encoding="utf-8")
    _install_engine_probe()
    try:
        for seed in SEED_OUT:
            _run_autoplay(seed)
    finally:
        _restore_engine()

    results = {}
    for seed, out in SEED_OUT.items():
        results[seed] = _replay(seed, out)
        _assert_complete(results[seed], seed)
    return results


def test_autoplay_present_and_executable(live_clears):
    """Checks that autoplay.js exists and was used to produce all seed clears."""
    assert AUTOPLAY.is_file()
    assert set(live_clears) == set(SEED_OUT)


def test_floor_span(live_clears):
    """Checks that all five floors are cleared on the nominal run."""
    data = live_clears["nominal"]
    assert data["floors_cleared"] == 5


def test_open_flag(live_clears):
    """Checks that open_flag_epoch was raised before completion."""
    assert int(live_clears["nominal"]["open_flag_epoch"]) >= 1


def test_stage_done(live_clears):
    """Checks that apex_stage reports cleared after a full run."""
    assert live_clears["nominal"]["apex_stage"] == "cleared"


def test_digest_ok(live_clears):
    """Checks that exit_seal_digest matches the public seal formula with used_chain."""
    data = live_clears["nominal"]
    expected = _seal(
        "nominal",
        int(data["floors_cleared"]),
        str(data["apex_stage"]),
        int(data["turns_used"]),
        str(data["used_chain"]),
    )
    assert data["exit_seal_digest"] == expected
    assert data["used_chain"] == CHAIN


def test_alt_layout(live_clears):
    """Checks that the holdout layout completes under a freshly driven transcript."""
    _assert_complete(live_clears["holdout"], "holdout")


def test_mirror_layout(live_clears):
    """Checks that the mirror layout completes under a freshly driven transcript."""
    _assert_complete(live_clears["mirror"], "mirror")


def test_rejects_static_handwrite(live_clears):
    """Forged JSON is overwritten when the transcript is replayed through the engine."""
    forged = {
        "seed": "nominal",
        "floors_cleared": 5,
        "open_flag_epoch": 1,
        "apex_stage": "cleared",
        "turns_used": BUDGET,
        "used_chain": CHAIN,
        "exit_seal_digest": _seal("nominal", 5, "cleared", BUDGET, CHAIN),
    }
    OUT.write_text(json.dumps(forged), encoding="utf-8")
    data = _replay("nominal", OUT)
    _assert_complete(data, "nominal")
    assert int(data["turns_used"]) < BUDGET


def test_autoplay_cli_seed_isolation(live_clears):
    """Re-runs autoplay on holdout into the documented holdout out path; seed must follow --seed."""
    _assert_autoplay_surface()
    _hit_log().write_text("", encoding="utf-8")
    _install_engine_probe()
    try:
        _run_autoplay("holdout", OUT_HOLDOUT)
        payload = json.loads(OUT_HOLDOUT.read_text(encoding="utf-8"))
        assert payload.get("seed") == "holdout"
    finally:
        _restore_engine()
        _replay("holdout", OUT_HOLDOUT)
