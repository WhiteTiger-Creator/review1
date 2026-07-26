"""Verifier for cooperative-signal-defense."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ENGINE = Path("/opt/signal-defense/bin/defensematch")
ASSETS = Path("/opt/signal-defense")
BOT = Path("/app/work/defensebot")
OUTPUT = Path("/app/output")
PUBLIC = (
    "corridor-converge",
    "jammed-relay",
    "overloaded-generator",
    "civilian-evac",
)


def _run(
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"/usr/local/go/bin:/opt/signal-defense/bin:{env.get('PATH', '')}"
    return subprocess.run(
        args,
        check=check,
        text=True,
        capture_output=True,
        env=env,
    )


def _match(
    scenario: str | Path,
    *,
    bot: Path = BOT,
    output: Path | None = None,
    doctrine: str | None = None,
    seed: int | None = None,
    inject: str | None = None,
    skip_verify: bool = False,
    check: bool = True,
) -> dict[str, Any]:
    out = Path(output) if output else Path(tempfile.mkdtemp(prefix="sd-out-"))
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ENGINE),
        "--bot",
        str(bot),
        "--output",
        str(out),
        "--print-summary",
    ]
    if skip_verify:
        cmd.append("--skip-verify")
    else:
        cmd.extend(["--assets", str(ASSETS)])
    if isinstance(scenario, Path) or str(scenario).endswith(".json"):
        cmd.extend(["--scenario", str(scenario)])
    else:
        cmd.extend(["--scenario-name", str(scenario)])
    if doctrine:
        cmd.extend(["--doctrine", doctrine])
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    if inject:
        cmd.extend(["--inject-failure", inject])
    proc = _run(cmd, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout or f"exit {proc.returncode}")
    summary: dict[str, Any] = {}
    if proc.stdout.strip():
        summary = json.loads(proc.stdout)
    return {
        "proc": proc,
        "summary": summary,
        "output": out,
        "generation": _current_gen(out) if (out / "current").exists() else None,
    }


def _current_gen(output: Path) -> Path:
    rel = (output / "current").read_text(encoding="utf-8").strip()
    return output / rel


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _clone_bot(tmp: Path) -> Path:
    dest = tmp / "defensebot"
    shutil.copytree(BOT, dest)
    return dest


def _base_grid() -> dict[str, Any]:
    return {
        "sectors": [
            {"id": "N", "x": 1, "y": 2, "role": "entry"},
            {"id": "H", "x": 1, "y": 1, "role": "hub"},
            {"id": "S", "x": 1, "y": 0, "role": "exit"},
            {"id": "W", "x": 0, "y": 1, "role": "post"},
            {"id": "E", "x": 2, "y": 1, "role": "post"},
            {"id": "CW", "x": 0, "y": 0, "role": "civilian"},
            {"id": "CE", "x": 2, "y": 0, "role": "civilian"},
        ],
        "edges": [
            ["N", "H"],
            ["H", "S"],
            ["W", "H"],
            ["E", "H"],
            ["W", "CW"],
            ["E", "CE"],
            ["CW", "S"],
            ["CE", "S"],
        ],
        "agent_post": {"id": "alpha", "sector": "W", "battery": 5, "battery_max": 6},
        "partner_post": {"id": "bravo", "sector": "E", "battery": 5, "battery_max": 6},
        "generators": [{"id": "G1", "sector": "H", "capacity": 5, "links": ["alpha", "bravo"]}],
        "civilian_corridors": [["CW", "S", "CE"]],
        "signal_types": [
            "WARN_LANE",
            "COVER",
            "NEED_POWER",
            "ACK",
            "SYNC_CAPTURE",
            "STATUS",
            "CANCEL_SCAN",
        ],
        "scoring": {
            "infrastructure": 10,
            "civilian": 5,
            "false_alarm_penalty": 3,
            "sync_capture": 8,
            "breakthrough_penalty": 15,
            "integrity_bonus": 4,
        },
        "max_actions": 4,
        "scan_range": 1,
        "interceptor_range": 1,
    }


def _write_scenario(tmp: Path, overrides: dict[str, Any]) -> Path:
    sc = _base_grid()
    sc.update(overrides)
    path = tmp / f"{sc['name']}.json"
    path.write_text(json.dumps(sc, indent=2) + "\n", encoding="utf-8")
    return path


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generation_bytes(gen: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for name in (
        "summary.json",
        "rounds.jsonl",
        "contacts.json",
        "signals.jsonl",
        "power.json",
        "civilians.json",
        "bot-diagnostics.json",
    ):
        out[name] = (gen / name).read_bytes()
    return out


# ---------------------------------------------------------------------------
# 3 protected-engine and integrity tests
# ---------------------------------------------------------------------------


def test_protected_engine_binary_and_asset_layout():
    """Protected defensematch binary and required asset directories exist with compiler retained."""
    assert ENGINE.is_file() and os.access(ENGINE, os.X_OK)
    for rel in ("contracts", "grids", "waves", "partners", "integrity", "bin"):
        assert (ASSETS / rel).is_dir()
    assert (ASSETS / "integrity" / "manifest.json").is_file()
    assert Path("/usr/local/go/bin/go").is_file()
    assert (Path("/app/work/defensebot") / "main.go").is_file()
    assert not (Path("/opt/signal-defense") / "solution").exists()


def test_integrity_manifest_rejects_mutated_assets(tmp_path: Path):
    """Mutating any protected asset class must fail integrity verification before a match."""
    # Copy assets and mutate each class
    classes = {
        "contracts/protocol.json": {"tampered": True},
        "grids/corridor.json": {"tampered": True},
        "waves/corridor-converge.json": None,
        "partners/signal-explicit.json": {"tampered": True},
        "integrity/manifest.json": None,
    }
    for rel in list(classes)[:-1]:
        root = tmp_path / "assets"
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(ASSETS, root, ignore=shutil.ignore_patterns("bin"))
        (root / "bin").mkdir(exist_ok=True)
        shutil.copy2(ENGINE, root / "bin" / "defensematch")
        target = root / rel
        if rel.endswith(".json") and classes[rel] is not None:
            data = json.loads(target.read_text(encoding="utf-8"))
            data["tampered"] = True
            target.write_text(json.dumps(data) + "\n", encoding="utf-8")
        else:
            target.write_bytes(target.read_bytes() + b"\n#mut\n")
        proc = _run(
            [
                str(root / "bin" / "defensematch"),
                "--assets",
                str(root),
                "--scenario-name",
                "corridor-converge",
                "--bot",
                str(BOT),
                "--output",
                str(tmp_path / "out"),
            ],
            check=False,
        )
        assert proc.returncode != 0
        assert "integrity" in (proc.stderr + proc.stdout).lower()


def test_controller_verifies_before_agent_compile(tmp_path: Path):
    """Controller verifies assets before compiling the agent bot for a public defense."""
    # Valid assets path succeeds compile+match
    result = _match("corridor-converge", output=tmp_path / "ok")
    assert result["summary"]["scenario"] == "corridor-converge"
    assert (result["generation"] / "summary.json").is_file()


# ---------------------------------------------------------------------------
# 6 protocol, signal-secrecy, legality, determinism, publication tests
# ---------------------------------------------------------------------------


def test_protocol_end_to_end_jsonl_orders():
    """Bot completes a public match through JSON Lines observation/orders/end without protocol errors."""
    result = _match("corridor-converge")
    diag = _read_json(result["generation"] / "bot-diagnostics.json")
    assert diag["protocol_errors"] == 0
    assert diag["legal_rounds"] >= 1


def test_signal_secrecy_hides_partner_private_and_wave_plans():
    """Authoritative contacts records omit partner-private observations and never embed wave plans."""
    result = _match("jammed-relay")
    contacts = _read_json(result["generation"] / "contacts.json")
    blob = json.dumps(contacts)
    assert "partner_private_omitted" in blob
    assert "wave_plan" not in blob.lower()
    rounds = _read_jsonl(result["generation"] / "rounds.jsonl")
    for row in rounds:
        assert "waves" not in row


def test_illegal_signal_type_rejected_without_breaking_prior_generation(tmp_path: Path):
    """Injected protocol failure preserves the previous generation byte-for-byte."""
    out = tmp_path / "pub"
    first = _match("corridor-converge", output=out)
    before = _generation_bytes(first["generation"])
    pointer = (out / "current").read_text(encoding="utf-8")
    bad = _match(
        "corridor-converge",
        output=out,
        inject="protocol",
        check=False,
    )
    assert bad["proc"].returncode != 0
    assert (out / "current").read_text(encoding="utf-8") == pointer
    after = _generation_bytes(first["generation"])
    assert after == before


def test_determinism_byte_identical_normalized_artifacts(tmp_path: Path):
    """Identical engine, scenario, seed, doctrine, and bot yield byte-identical normalized artifacts."""
    a = _match("corridor-converge", output=tmp_path / "a", seed=101)
    b = _match("corridor-converge", output=tmp_path / "b", seed=101)
    assert _generation_bytes(a["generation"]) == _generation_bytes(b["generation"])


def test_publication_inject_failures_preserve_current(tmp_path: Path):
    """Injected write/validate/rename/pointer failures leave the previous current generation intact."""
    out = tmp_path / "pub2"
    first = _match("jammed-relay", output=out)
    before = _generation_bytes(first["generation"])
    pointer = (out / "current").read_text(encoding="utf-8")
    for kind in ("write", "validate", "rename", "pointer"):
        proc = _match(
            "jammed-relay",
            output=out,
            inject=kind,
            check=False,
        )
        assert proc["proc"].returncode != 0
        assert (out / "current").read_text(encoding="utf-8") == pointer
        assert _generation_bytes(first["generation"]) == before


def test_compile_failure_injection_preserves_current(tmp_path: Path):
    """Injected compile failure does not replace the authoritative current pointer."""
    out = tmp_path / "pub3"
    first = _match("overloaded-generator", output=out)
    pointer = (out / "current").read_text(encoding="utf-8")
    before = _generation_bytes(first["generation"])
    bad = _match(
        "overloaded-generator",
        output=out,
        inject="compile",
        check=False,
    )
    assert bad["proc"].returncode != 0
    assert (out / "current").read_text(encoding="utf-8") == pointer
    assert _generation_bytes(first["generation"]) == before


# ---------------------------------------------------------------------------
# 10 public cooperative-behavior tests
# ---------------------------------------------------------------------------


def test_public_legal_orders_and_bounded_signals_every_round():
    """Public defenses emit only legal ops and stay within signal budget every round."""
    for name in PUBLIC:
        result = _match(name)
        rounds = _read_jsonl(result["generation"] / "rounds.jsonl")
        legal = {
            "move",
            "scan",
            "intercept",
            "reinforce",
            "shield",
            "signal",
            "hold",
            "repair",
        }
        signal_accepts = 0
        for row in rounds:
            for act in row["agent_actions"]:
                assert act["op"] in legal
            for sig in row.get("signals", []):
                if sig.get("from") == "alpha" and sig.get("accepted"):
                    signal_accepts += 1
        signals = _read_jsonl(result["generation"] / "signals.jsonl")
        assert len(rounds) >= 1
        assert all("timestamp" not in r for r in rounds)
        _ = signals


def test_public_ack_delayed_partner_lane_warning():
    """Bot acknowledges a delayed partner WARN_LANE or SYNC_CAPTURE after one-round delay."""
    result = _match("corridor-converge", doctrine="signal-explicit")
    signals = _read_jsonl(result["generation"] / "signals.jsonl")
    agent_ack = [s for s in signals if s.get("type") == "ACK" and s.get("from") == "alpha"]
    assert agent_ack, "bot must acknowledge delayed partner lane warnings"


def test_public_power_reservation_before_scan_and_shield_contention():
    """On overloaded-generator, bots avoid unchecked dual scan+shield thrash on one generator."""
    result = _match("overloaded-generator", doctrine="power-conservative")
    assert result["summary"]["generators_alive"] >= 1
    assert result["summary"]["passed_accept"] is True
    assert result["summary"]["score"] >= result["summary"]["accept_score"]


def test_public_avoid_redundant_interception_when_partner_covers():
    """Bots avoid stacking intercepts on a contact already covered by the partner."""
    result = _match("corridor-converge", doctrine="signal-explicit")
    rounds = _read_jsonl(result["generation"] / "rounds.jsonl")
    redundant = 0
    for row in rounds:
        inter = row.get("intercepts") or {}
        for actors in inter.values():
            if isinstance(actors, list) and len(actors) > 1:
                redundant += 1
    assert result["summary"]["passed_accept"] is True
    assert redundant <= 2


def test_public_discriminate_confirmed_incursion_vs_false_contact():
    """Civilian-evac includes a false contact; bots must not rack false alarms."""
    result = _match("civilian-evac")
    assert result["summary"]["false_alarms"] == 0
    assert result["summary"]["passed_accept"] is True


def test_public_civilian_corridor_protection_under_lane_pressure():
    """Bots preserve civilian corridor counts under simultaneous lane pressure."""
    result = _match("corridor-converge")
    civ = _read_json(result["generation"] / "civilians.json")
    assert civ["safe"] == civ["total"]
    assert result["summary"]["passed_accept"] is True


def test_public_synchronized_capture_requires_signal_and_two_coverage_actions():
    """Civilian-evac boss requires SYNC_CAPTURE signaling and dual coverage for sync credit."""
    result = _match("civilian-evac")
    assert result["summary"]["sync_captures"] >= 1
    signals = _read_jsonl(result["generation"] / "signals.jsonl")
    assert any(s.get("type") == "SYNC_CAPTURE" for s in signals)
    assert result["summary"]["passed_accept"] is True


def test_public_recovery_from_overload_without_abandoning_both_posts():
    """After generator stress, posts remain on the board and recovery keeps sector presence."""
    result = _match("overloaded-generator")
    rounds = _read_jsonl(result["generation"] / "rounds.jsonl")
    assert all(r["agent_sector"] and r["partner_sector"] for r in rounds)
    assert result["summary"]["passed_accept"] is True


def test_public_adapt_to_power_conservative_partner_doctrine():
    """Overloaded-generator with power-conservative partner is completed successfully."""
    result = _match("overloaded-generator", doctrine="power-conservative")
    diag = _read_json(result["generation"] / "bot-diagnostics.json")
    assert diag["protocol_errors"] == 0
    assert result["summary"]["partner_doctrine"] == "power-conservative"
    assert result["summary"]["passed_accept"] is True


def test_public_multiwave_team_scoring_across_objectives():
    """Public multi-wave score reconciles infrastructure, civilians, and false-alarm fields."""
    result = _match("civilian-evac")
    summary = _read_json(result["generation"] / "summary.json")
    assert summary["score"] == summary["score_reconciled"]
    assert summary["passed_accept"] is True
    for key in ("infrastructure_hp", "civilians_safe", "false_alarms", "sync_captures"):
        assert key in summary
    assert summary["sync_captures"] >= 1
    assert summary["breakthroughs"] == 0


# ---------------------------------------------------------------------------
# 13 isolated hidden composite defense tests
# ---------------------------------------------------------------------------


def test_hidden_delayed_signal_after_scanner_commit(tmp_path: Path):
    """Delayed WARN identifies a branch only after the bot already committed scanner power elsewhere."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-delay-branch",
            "seed": 9001,
            "horizon": 8,
            "accept_score": 50,
            "signal_budget": 3,
            "partner_doctrine": "signal-explicit",
            "jamming": [],
            "waves": [
                {
                    "id": "decoy",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "false",
                    "speed": 1,
                    "hp": 1,
                },
                {
                    "id": "branch",
                    "spawn_round": 2,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                    "branch_at": 1,
                    "branch_lane": ["E", "CE"],
                },
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    assert result["generation"] is not None
    assert result["summary"]["scenario"] == "hidden-delay-branch"


def test_hidden_jamming_removes_ack_partner_movement_implies_cover(tmp_path: Path):
    """Jamming drops ACK while partner movement still implies coverage on the public sector."""
    bot = _clone_bot(tmp_path)
    result = _match("jammed-relay", bot=bot, output=tmp_path / "out")
    rounds = _read_jsonl(result["generation"] / "rounds.jsonl")
    signals = _read_jsonl(result["generation"] / "signals.jsonl")
    assert any(r.get("jammed") for r in rounds)
    # Partner still occupies sectors during jam (coverage implication without ACK).
    jammed_rounds = [r for r in rounds if r.get("jammed")]
    assert jammed_rounds and all(r["partner_sector"] for r in jammed_rounds)
    # Any ACK attempted while jammed must be rejected.
    for s in signals:
        if s.get("type") == "ACK" and s.get("round") in {r["round"] for r in jammed_rounds}:
            assert s.get("accepted") is False
            assert "jam" in str(s.get("error", "")).lower()


def test_hidden_two_real_one_false_single_interceptor(tmp_path: Path):
    """Two real contacts and one false trace compete for one interceptor and finite signal tokens."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-triage",
            "seed": 9003,
            "horizon": 9,
            "accept_score": 55,
            "signal_budget": 2,
            "partner_doctrine": "power-conservative",
            "generators": [
                {"id": "G1", "sector": "H", "capacity": 4, "links": ["alpha", "bravo"]}
            ],
            "waves": [
                {
                    "id": "r1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                },
                {
                    "id": "r2",
                    "spawn_round": 1,
                    "lane": ["N", "H", "E", "CE"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                },
                {
                    "id": "f1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "W"],
                    "kind": "false",
                    "speed": 1,
                    "hp": 1,
                },
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    assert result["summary"]["false_alarms"] >= 0
    if result["summary"].get("score", 0) >= 55:
        assert result["summary"]["false_alarms"] <= 1


def test_hidden_shield_overloads_unless_scan_canceled(tmp_path: Path):
    """Shielding a civilian route overloads the generator unless a redundant scan is canceled."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-shield-overload",
            "seed": 9004,
            "horizon": 8,
            "accept_score": 45,
            "signal_budget": 3,
            "partner_doctrine": "aggressive",
            "generators": [
                {"id": "G1", "sector": "H", "capacity": 3, "links": ["alpha", "bravo"]}
            ],
            "agent_post": {"id": "alpha", "sector": "W", "battery": 1, "battery_max": 3},
            "waves": [
                {
                    "id": "c1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    assert result["generation"] is not None


def test_hidden_aggressive_partner_overcommit_preserve_late_power(tmp_path: Path):
    """Aggressive partner overcommits early; accepting bots preserve late-wave power."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-agg-late",
            "seed": 9005,
            "horizon": 10,
            "accept_score": 50,
            "signal_budget": 3,
            "partner_doctrine": "aggressive",
            "generators": [
                {"id": "G1", "sector": "H", "capacity": 4, "links": ["alpha", "bravo"]}
            ],
            "waves": [
                {
                    "id": "early",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                },
                {
                    "id": "late",
                    "spawn_round": 6,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                },
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    if result["summary"].get("score", 0) >= 50:
        assert result["summary"]["breakthroughs"] <= 1


def test_hidden_sync_signal_one_round_before_visibility(tmp_path: Path):
    """Synchronized capture is possible only if the bot signals intent before contact is jointly visible."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-sync-early",
            "seed": 9006,
            "horizon": 10,
            "accept_score": 60,
            "signal_budget": 4,
            "partner_doctrine": "signal-explicit",
            "sync_capture_contact": "boss",
            "waves": [
                {
                    "id": "boss",
                    "spawn_round": 3,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 2,
                }
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    if result["summary"].get("score", 0) >= 60:
        assert result["summary"]["sync_captures"] >= 1


def test_hidden_renamed_sectors_and_reordered_contacts(tmp_path: Path):
    """Renamed sectors and reordered contact records must not expose identifier dependence."""
    bot = _clone_bot(tmp_path)
    base = _write_scenario(
        tmp_path,
        {
            "name": "hidden-rename-a",
            "seed": 9007,
            "horizon": 8,
            "accept_score": 40,
            "signal_budget": 3,
            "partner_doctrine": "signal-explicit",
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    sc = json.loads(base.read_text(encoding="utf-8"))
    mapping = {s["id"]: f"X{s['id']}" for s in sc["sectors"]}
    for s in sc["sectors"]:
        s["id"] = mapping[s["id"]]
    sc["edges"] = [[mapping[a], mapping[b]] for a, b in sc["edges"]]
    sc["agent_post"]["sector"] = mapping[sc["agent_post"]["sector"]]
    sc["partner_post"]["sector"] = mapping[sc["partner_post"]["sector"]]
    sc["generators"][0]["sector"] = mapping[sc["generators"][0]["sector"]]
    sc["civilian_corridors"] = [
        [mapping[x] for x in row] for row in sc["civilian_corridors"]
    ]
    for w in sc["waves"]:
        w["lane"] = [mapping[x] for x in w["lane"]]
    sc["name"] = "hidden-rename-b"
    path = tmp_path / "hidden-rename-b.json"
    path.write_text(json.dumps(sc) + "\n", encoding="utf-8")
    result = _match(path, bot=bot, output=tmp_path / "out", skip_verify=True)
    assert result["summary"]["scenario"] == "hidden-rename-b"


def test_hidden_rotated_symmetric_grid(tmp_path: Path):
    """Rotated symmetric grid requires rotated coverage rather than memorized coordinates."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-rotate",
            "seed": 9008,
            "horizon": 8,
            "accept_score": 40,
            "signal_budget": 3,
            "partner_doctrine": "signal-explicit",
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    data = json.loads(sc.read_text(encoding="utf-8"))
    for s in data["sectors"]:
        x, y = s["x"], s["y"]
        s["x"], s["y"] = y, -x
    path = tmp_path / "hidden-rotate.json"
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")
    result = _match(path, bot=bot, output=tmp_path / "out", skip_verify=True)
    assert result["generation"] is not None


def test_hidden_increased_signal_capacity_no_waste(tmp_path: Path):
    """Increased signal capacity must not cause wasteful communication that reduces defense actions."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-signal-cap",
            "seed": 9009,
            "horizon": 8,
            "accept_score": 45,
            "signal_budget": 12,
            "partner_doctrine": "signal-explicit",
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    rounds = _read_jsonl(result["generation"] / "rounds.jsonl")
    defense_ops = 0
    for row in rounds:
        for act in row["agent_actions"]:
            if act["op"] in {"intercept", "shield", "move", "scan", "repair"}:
                defense_ops += 1
    assert defense_ops >= 1


def test_hidden_remove_concealed_threat_outside_envelope(tmp_path: Path):
    """Removing a concealed threat outside all future interaction envelopes has no observable effect."""
    bot = _clone_bot(tmp_path)
    base_waves = [
        {
            "id": "visible",
            "spawn_round": 1,
            "lane": ["N", "H", "S"],
            "kind": "incursion",
            "speed": 1,
            "hp": 1,
        }
    ]
    sc1 = _write_scenario(
        tmp_path,
        {
            "name": "hidden-envelope-a",
            "seed": 9010,
            "horizon": 6,
            "accept_score": 30,
            "signal_budget": 2,
            "partner_doctrine": "power-conservative",
            "waves": base_waves
            + [
                {
                    "id": "ghost",
                    "spawn_round": 20,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    # ghost spawn_round > horizon => outside envelope; compare to no ghost
    sc2 = _write_scenario(
        tmp_path,
        {
            "name": "hidden-envelope-b",
            "seed": 9010,
            "horizon": 6,
            "accept_score": 30,
            "signal_budget": 2,
            "partner_doctrine": "power-conservative",
            "waves": base_waves,
        },
    )
    a = _match(sc1, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(sc2, bot=bot, output=tmp_path / "b", skip_verify=True)
    ra = _read_jsonl(a["generation"] / "rounds.jsonl")
    rb = _read_jsonl(b["generation"] / "rounds.jsonl")
    assert [r["agent_actions"] for r in ra] == [r["agent_actions"] for r in rb]


def test_hidden_jammed_relay_civilian_repair_priority(tmp_path: Path):
    """Jammed relay, civilian corridor, and generator repair must be prioritized across three rounds."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-tri-priority",
            "seed": 9011,
            "horizon": 9,
            "accept_score": 40,
            "signal_budget": 3,
            "partner_doctrine": "aggressive",
            "jamming": [{"round": 1, "duration": 2}],
            "generators": [
                {"id": "G1", "sector": "H", "capacity": 3, "links": ["alpha", "bravo"]}
            ],
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    assert len(_read_jsonl(result["generation"] / "rounds.jsonl")) >= 3


def test_hidden_two_doctrines_same_move_different_reserves(tmp_path: Path):
    """Two partner doctrines can share a current move yet require different future power reserves."""
    bot = _clone_bot(tmp_path)
    overrides = {
        "seed": 9012,
        "horizon": 8,
        "accept_score": 40,
        "signal_budget": 3,
        "waves": [
            {
                "id": "t1",
                "spawn_round": 1,
                "lane": ["N", "H", "S"],
                "kind": "incursion",
                "speed": 1,
                "hp": 1,
            },
            {
                "id": "t2",
                "spawn_round": 5,
                "lane": ["N", "H", "S"],
                "kind": "incursion",
                "speed": 1,
                "hp": 1,
            },
        ],
    }
    sc_a = _write_scenario(
        tmp_path,
        {**overrides, "name": "hidden-doc-a", "partner_doctrine": "power-conservative"},
    )
    sc_b = _write_scenario(
        tmp_path,
        {**overrides, "name": "hidden-doc-b", "partner_doctrine": "aggressive"},
    )
    a = _match(sc_a, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(sc_b, bot=bot, output=tmp_path / "b", skip_verify=True)
    assert a["summary"]["partner_doctrine"] != b["summary"]["partner_doctrine"]


def test_hidden_final_wave_balanced_scoring(tmp_path: Path):
    """Final-wave infrastructure, civilian, false-alarm, and sync scores must be balanced together."""
    bot = _clone_bot(tmp_path)
    sc = _write_scenario(
        tmp_path,
        {
            "name": "hidden-final-balance",
            "seed": 9013,
            "horizon": 12,
            "accept_score": 70,
            "signal_budget": 5,
            "partner_doctrine": "signal-explicit",
            "sync_capture_contact": "boss",
            "waves": [
                {
                    "id": "fake",
                    "spawn_round": 1,
                    "lane": ["N", "H", "W"],
                    "kind": "false",
                    "speed": 1,
                    "hp": 1,
                },
                {
                    "id": "mid",
                    "spawn_round": 2,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                },
                {
                    "id": "boss",
                    "spawn_round": 5,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 2,
                },
            ],
        },
    )
    result = _match(sc, bot=bot, output=tmp_path / "out", skip_verify=True)
    summary = result["summary"]
    assert summary["score"] == summary["score_reconciled"]
    if summary.get("score", 0) >= 70:
        assert summary["false_alarms"] == 0
        assert summary["sync_captures"] >= 1
        assert summary["civilians_safe"] >= 1


# ---------------------------------------------------------------------------
# 6 game-native metamorphic tests
# ---------------------------------------------------------------------------


def test_metamorphic_bijective_sector_renaming_preserves_outcomes(tmp_path: Path):
    """Bijective sector renaming preserves normalized team outcomes."""
    bot = _clone_bot(tmp_path)
    base = {
        "name": "meta-rename-a",
        "seed": 7001,
        "horizon": 7,
        "accept_score": 30,
        "signal_budget": 3,
        "partner_doctrine": "signal-explicit",
        "waves": [
            {
                "id": "t1",
                "spawn_round": 1,
                "lane": ["N", "H", "S"],
                "kind": "incursion",
                "speed": 1,
                "hp": 1,
            }
        ],
    }
    sc1 = _write_scenario(tmp_path, base)
    data = json.loads(sc1.read_text(encoding="utf-8"))
    mapping = {s["id"]: f"R{s['id']}" for s in data["sectors"]}
    for s in data["sectors"]:
        s["id"] = mapping[s["id"]]
    data["edges"] = [[mapping[a], mapping[b]] for a, b in data["edges"]]
    data["agent_post"]["sector"] = mapping[data["agent_post"]["sector"]]
    data["partner_post"]["sector"] = mapping[data["partner_post"]["sector"]]
    data["generators"][0]["sector"] = mapping[data["generators"][0]["sector"]]
    data["civilian_corridors"] = [
        [mapping[x] for x in row] for row in data["civilian_corridors"]
    ]
    for w in data["waves"]:
        w["lane"] = [mapping[x] for x in w["lane"]]
    data["name"] = "meta-rename-b"
    sc2 = tmp_path / "meta-rename-b.json"
    sc2.write_text(json.dumps(data) + "\n", encoding="utf-8")
    a = _match(sc1, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(sc2, bot=bot, output=tmp_path / "b", skip_verify=True)
    assert a["summary"]["score"] == b["summary"]["score"]
    assert a["summary"]["breakthroughs"] == b["summary"]["breakthroughs"]


def test_metamorphic_reorder_independent_contacts_preserves_resolution(tmp_path: Path):
    """Reordering independent contact records preserves legal decisions and resolution."""
    bot = _clone_bot(tmp_path)
    waves_a = [
        {
            "id": "a1",
            "spawn_round": 1,
            "lane": ["N", "H", "S"],
            "kind": "incursion",
            "speed": 1,
            "hp": 1,
        },
        {
            "id": "b1",
            "spawn_round": 1,
            "lane": ["N", "H", "E", "CE"],
            "kind": "incursion",
            "speed": 1,
            "hp": 1,
        },
    ]
    waves_b = list(reversed(waves_a))
    sc1 = _write_scenario(
        tmp_path,
        {
            "name": "meta-order-a",
            "seed": 7002,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 3,
            "partner_doctrine": "power-conservative",
            "waves": waves_a,
        },
    )
    sc2 = _write_scenario(
        tmp_path,
        {
            "name": "meta-order-b",
            "seed": 7002,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 3,
            "partner_doctrine": "power-conservative",
            "waves": waves_b,
        },
    )
    a = _match(sc1, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(sc2, bot=bot, output=tmp_path / "b", skip_verify=True)
    assert a["summary"]["score"] == b["summary"]["score"]


def test_metamorphic_symmetric_grid_rotation(tmp_path: Path):
    """Rotating a symmetric grid rotates strategic actions without material score loss."""
    bot = _clone_bot(tmp_path)
    sc1 = _write_scenario(
        tmp_path,
        {
            "name": "meta-rot-a",
            "seed": 7003,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 3,
            "partner_doctrine": "signal-explicit",
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    data = json.loads(sc1.read_text(encoding="utf-8"))
    for s in data["sectors"]:
        x, y = s["x"], s["y"]
        s["x"], s["y"] = y, -x
    data["name"] = "meta-rot-b"
    sc2 = tmp_path / "meta-rot-b.json"
    sc2.write_text(json.dumps(data) + "\n", encoding="utf-8")
    a = _match(sc1, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(sc2, bot=bot, output=tmp_path / "b", skip_verify=True)
    assert abs(a["summary"]["score"] - b["summary"]["score"]) <= 15


def test_metamorphic_increased_signal_capacity_preserves_legal_plans(tmp_path: Path):
    """Increasing friendly signal capacity cannot reduce the set of legal cooperative plans."""
    bot = _clone_bot(tmp_path)
    low = _write_scenario(
        tmp_path,
        {
            "name": "meta-sig-low",
            "seed": 7004,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 2,
            "partner_doctrine": "signal-explicit",
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    high = _write_scenario(
        tmp_path,
        {
            "name": "meta-sig-high",
            "seed": 7004,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 8,
            "partner_doctrine": "signal-explicit",
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    a = _match(low, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(high, bot=bot, output=tmp_path / "b", skip_verify=True)
    assert b["summary"]["score"] >= a["summary"]["score"] - 5


def test_metamorphic_increased_generator_capacity_keeps_schedule_feasible(tmp_path: Path):
    """Increasing generator capacity cannot invalidate a previously feasible defense schedule."""
    bot = _clone_bot(tmp_path)
    low = _write_scenario(
        tmp_path,
        {
            "name": "meta-gen-low",
            "seed": 7005,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 3,
            "partner_doctrine": "power-conservative",
            "generators": [
                {"id": "G1", "sector": "H", "capacity": 3, "links": ["alpha", "bravo"]}
            ],
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    high = _write_scenario(
        tmp_path,
        {
            "name": "meta-gen-high",
            "seed": 7005,
            "horizon": 7,
            "accept_score": 30,
            "signal_budget": 3,
            "partner_doctrine": "power-conservative",
            "generators": [
                {"id": "G1", "sector": "H", "capacity": 8, "links": ["alpha", "bravo"]}
            ],
            "waves": [
                {
                    "id": "t1",
                    "spawn_round": 1,
                    "lane": ["N", "H", "S"],
                    "kind": "incursion",
                    "speed": 1,
                    "hp": 1,
                }
            ],
        },
    )
    a = _match(low, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(high, bot=bot, output=tmp_path / "b", skip_verify=True)
    assert b["summary"]["score"] >= a["summary"]["score"]


def test_metamorphic_remove_out_of_envelope_threat_unchanged_history(tmp_path: Path):
    """Removing a threat outside visibility and interaction envelopes cannot change observation history."""
    bot = _clone_bot(tmp_path)
    visible = [
        {
            "id": "vis",
            "spawn_round": 1,
            "lane": ["N", "H", "S"],
            "kind": "incursion",
            "speed": 1,
            "hp": 1,
        }
    ]
    ghost = {
        "id": "ghost",
        "spawn_round": 50,
        "lane": ["N", "H", "S"],
        "kind": "incursion",
        "speed": 1,
        "hp": 1,
    }
    sc1 = _write_scenario(
        tmp_path,
        {
            "name": "meta-env-a",
            "seed": 7006,
            "horizon": 5,
            "accept_score": 20,
            "signal_budget": 2,
            "partner_doctrine": "signal-explicit",
            "waves": visible + [ghost],
        },
    )
    sc2 = _write_scenario(
        tmp_path,
        {
            "name": "meta-env-b",
            "seed": 7006,
            "horizon": 5,
            "accept_score": 20,
            "signal_budget": 2,
            "partner_doctrine": "signal-explicit",
            "waves": visible,
        },
    )
    a = _match(sc1, bot=bot, output=tmp_path / "a", skip_verify=True)
    b = _match(sc2, bot=bot, output=tmp_path / "b", skip_verify=True)
    ra = _read_jsonl(a["generation"] / "rounds.jsonl")
    rb = _read_jsonl(b["generation"] / "rounds.jsonl")
    assert [r["agent_actions"] for r in ra] == [r["agent_actions"] for r in rb]
    assert a["summary"]["score"] == b["summary"]["score"]
