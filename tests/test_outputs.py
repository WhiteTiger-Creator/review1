"""Verifier for Tak road/flat championship report output."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

SCENARIOS = Path("/app/scenarios")
OUTPUT = Path("/app/output/championship_report.json")
CONTRACT = Path("/app/contracts/championship-ruleset.md")
PROFILE = Path("/app/config/profiles/champ-v3/rules.toml")
PROFILE_NAME = Path("/app/config/profile.name")
RUNTIME_OVERLAY = Path("/app/config/runtime/champ-v3.floor.toml")
BINARY = Path("/app/bin/tak-road")

RUN_ID = "tak-champ-v1"
CORRECT_SEAL = "cc7af441d8baf8187d315a615cbcb3f4424cc5499d54c65e4b590b9a7f4264a8"
CORRECT = {
    "run_id": RUN_ID,
    "board_size": 5,
    "road_ortho": 1,
    "caps_on_road": 1,
    "caps_on_flat": 1,
    "walls_on_flat": 0,
    "flat_margin": 3,
    "win_points": 3,
    "draw_points": 1,
}

SCENARIO_SHA256 = {
    "m01.json": "44e90cf75f3ab9c2885fe5dceb053d9788cce9839eb9039c69ebceb1c8d3fd73",
    "m02.json": "0e7985dde2b7fb98771b34b094c740766607128a96850bf8538b23d5f6f78387",
    "m03.json": "0922ae068807eed3158f0806dc54e61c2c54389a2a80d527c537c69cdf95235b",
    "m04.json": "027002af459ce6b0338af47e3508b973750d6d42f194e3090ba0e1d6c6068d65",
    "m05.json": "b55355b2a61f08b4ab8eeb33150ed6aba4759f59047ce4907a2ed9e8cd43e6c3",
    "m06.json": "d0f081f705964a96bd0ae22ce0456bac5988d1c7a9a5096b7bcff3c2a0825564",
    "m07.json": "20f9ecc9e9900498f0687ad22b9997a9e6770c0d7cb324d33be9dc38c40ecf69",
    "m08.json": "191cd9990c9c6c14d4289724d02738077888b92dd7c54772e66315ab65f4e8c2",
    "m09.json": "668338801c250c1738eebab461c847d8c57e289dfcca5d60d7bc5f2c2ce95017",
    "m10.json": "03241c86d1d3b995854c3b9ab6d56009246ed5d2385929544c2cb0a24bf3f619",
    "m11.json": "7e1fb981563f73e58348c717510d68e0f125d8a5616d52f1e8f3e345f5887943",
    "m12.json": "42d9afbb367138cb1485f3ccaee973d7f4b5af4f1d351ec6e80d1e1efc797136"
}

_GOLDEN = json.loads(
    r'''{
  "schema_version": "1.0",
  "run_id": "tak-champ-v1",
  "matches_played": 12,
  "matches": [
    {
      "match_id": "m01",
      "player_a": "stone_north",
      "player_b": "tide_east",
      "winner": "A",
      "reason": "road_complete",
      "flats_a": 5,
      "flats_b": 0,
      "road_a": 1,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "critical",
      "priority_score": 92,
      "related_ids": [
        "m02",
        "m03",
        "m04",
        "m06",
        "m07",
        "m10",
        "m11"
      ]
    },
    {
      "match_id": "m02",
      "player_a": "stone_north",
      "player_b": "tide_east",
      "winner": "B",
      "reason": "road_complete",
      "flats_a": 0,
      "flats_b": 5,
      "road_a": 0,
      "road_b": 1,
      "points_a": 0,
      "points_b": 3,
      "severity": "critical",
      "priority_score": 92,
      "related_ids": [
        "m01",
        "m03",
        "m04",
        "m06",
        "m07",
        "m10",
        "m11"
      ]
    },
    {
      "match_id": "m03",
      "player_a": "cap_ridge",
      "player_b": "tide_east",
      "winner": "A",
      "reason": "road_complete",
      "flats_a": 5,
      "flats_b": 0,
      "road_a": 1,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "critical",
      "priority_score": 92,
      "related_ids": [
        "m01",
        "m02",
        "m05",
        "m06",
        "m07",
        "m09",
        "m11"
      ]
    },
    {
      "match_id": "m04",
      "player_a": "stone_north",
      "player_b": "wall_guild",
      "winner": "A",
      "reason": "flat_majority",
      "flats_a": 4,
      "flats_b": 2,
      "road_a": 0,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "medium",
      "priority_score": 48,
      "related_ids": [
        "m01",
        "m02",
        "m05",
        "m06",
        "m08",
        "m10"
      ]
    },
    {
      "match_id": "m05",
      "player_a": "cap_ridge",
      "player_b": "wall_guild",
      "winner": "A",
      "reason": "flat_majority",
      "flats_a": 3,
      "flats_b": 2,
      "road_a": 0,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "medium",
      "priority_score": 48,
      "related_ids": [
        "m03",
        "m04",
        "m08",
        "m09",
        "m10"
      ]
    },
    {
      "match_id": "m06",
      "player_a": "stone_north",
      "player_b": "tide_east",
      "winner": "draw",
      "reason": "mutual_draw",
      "flats_a": 2,
      "flats_b": 2,
      "road_a": 0,
      "road_b": 0,
      "points_a": 1,
      "points_b": 1,
      "severity": "low",
      "priority_score": 20,
      "related_ids": [
        "m01",
        "m02",
        "m03",
        "m04",
        "m07",
        "m10",
        "m11"
      ]
    },
    {
      "match_id": "m07",
      "player_a": "flat_manor",
      "player_b": "tide_east",
      "winner": "B",
      "reason": "road_complete",
      "flats_a": 9,
      "flats_b": 5,
      "road_a": 0,
      "road_b": 1,
      "points_a": 0,
      "points_b": 3,
      "severity": "critical",
      "priority_score": 92,
      "related_ids": [
        "m01",
        "m02",
        "m03",
        "m06",
        "m09",
        "m11",
        "m12"
      ]
    },
    {
      "match_id": "m08",
      "player_a": "stack_ward",
      "player_b": "wall_guild",
      "winner": "A",
      "reason": "road_complete",
      "flats_a": 5,
      "flats_b": 0,
      "road_a": 1,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "critical",
      "priority_score": 92,
      "related_ids": [
        "m04",
        "m05",
        "m10"
      ]
    },
    {
      "match_id": "m09",
      "player_a": "cap_ridge",
      "player_b": "flat_manor",
      "winner": "A",
      "reason": "flat_clear",
      "flats_a": 4,
      "flats_b": 1,
      "road_a": 0,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "high",
      "priority_score": 70,
      "related_ids": [
        "m03",
        "m05",
        "m07",
        "m12"
      ]
    },
    {
      "match_id": "m10",
      "player_a": "stone_north",
      "player_b": "wall_guild",
      "winner": "A",
      "reason": "flat_majority",
      "flats_a": 2,
      "flats_b": 1,
      "road_a": 0,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "medium",
      "priority_score": 48,
      "related_ids": [
        "m01",
        "m02",
        "m04",
        "m05",
        "m06",
        "m08"
      ]
    },
    {
      "match_id": "m11",
      "player_a": "diag_club",
      "player_b": "tide_east",
      "winner": "A",
      "reason": "flat_clear",
      "flats_a": 5,
      "flats_b": 1,
      "road_a": 0,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "high",
      "priority_score": 70,
      "related_ids": [
        "m01",
        "m02",
        "m03",
        "m06",
        "m07",
        "m12"
      ]
    },
    {
      "match_id": "m12",
      "player_a": "flat_manor",
      "player_b": "diag_club",
      "winner": "A",
      "reason": "flat_clear",
      "flats_a": 4,
      "flats_b": 1,
      "road_a": 0,
      "road_b": 0,
      "points_a": 3,
      "points_b": 0,
      "severity": "high",
      "priority_score": 70,
      "related_ids": [
        "m07",
        "m09",
        "m11"
      ]
    }
  ],
  "standings": [
    {
      "player_id": "stone_north",
      "points": 10,
      "wins": 3,
      "draws": 1,
      "losses": 1,
      "flat_diff": 3,
      "rank": 1
    },
    {
      "player_id": "cap_ridge",
      "points": 9,
      "wins": 3,
      "draws": 0,
      "losses": 0,
      "flat_diff": 9,
      "rank": 2
    },
    {
      "player_id": "tide_east",
      "points": 7,
      "wins": 2,
      "draws": 1,
      "losses": 3,
      "flat_diff": -13,
      "rank": 3
    },
    {
      "player_id": "stack_ward",
      "points": 3,
      "wins": 1,
      "draws": 0,
      "losses": 0,
      "flat_diff": 5,
      "rank": 4
    },
    {
      "player_id": "flat_manor",
      "points": 3,
      "wins": 1,
      "draws": 0,
      "losses": 2,
      "flat_diff": 4,
      "rank": 5
    },
    {
      "player_id": "diag_club",
      "points": 3,
      "wins": 1,
      "draws": 0,
      "losses": 1,
      "flat_diff": 1,
      "rank": 6
    },
    {
      "player_id": "wall_guild",
      "points": 0,
      "wins": 0,
      "draws": 0,
      "losses": 4,
      "flat_diff": -9,
      "rank": 7
    }
  ],
  "summary": {
    "aggregate_priority": 83,
    "max_severity": "critical",
    "decisive_matches": 11,
    "draw_matches": 1
  }
}
'''
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_seal(cfg: dict) -> str:
    keys = [
        "run_id",
        "board_size",
        "road_ortho",
        "caps_on_road",
        "caps_on_flat",
        "walls_on_flat",
        "flat_margin",
        "win_points",
        "draw_points",
    ]
    payload = "".join(f"{k}={cfg[k]}\n" for k in keys)
    return hashlib.sha256(payload.encode()).hexdigest()


def _parse_profile(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def _score(reason: str) -> tuple[str, int]:
    return {
        "road_complete": ("critical", 92),
        "flat_clear": ("high", 70),
        "flat_majority": ("medium", 48),
        "mutual_draw": ("low", 20),
    }[reason]


def _run_engine() -> None:
    assert BINARY.is_file(), "tak-road binary missing"
    subprocess.run(
        [
            str(BINARY),
            "--scenarios",
            "/app/scenarios",
            "--config",
            "/app/config",
            "--out",
            "/app/output",
        ],
        check=True,
    )


def test_scenario_fixtures_unchanged():
    """Scenario JSON fixtures must keep their original SHA-256 digests."""
    for name, digest in SCENARIO_SHA256.items():
        assert _sha256(SCENARIOS / name) == digest


def test_contract_and_profile_name_present():
    """Ruleset contract and profile.name pointer must exist for championship ops."""
    assert CONTRACT.is_file()
    assert PROFILE_NAME.read_text().strip() == "champ-v3"


def test_sealed_profile_floors_and_seal():
    """Sealed champ-v3 profile must carry championship floors and matching seal."""
    raw = PROFILE.read_text()
    assert 'run_id = "tak-champ-v1"' in raw
    assert "board_size = 5" in raw
    assert "road_ortho = 1" in raw
    assert "caps_on_road = 1" in raw
    assert "caps_on_flat = 1" in raw
    assert "walls_on_flat = 0" in raw
    assert "flat_margin = 3" in raw
    assert "win_points = 3" in raw
    assert "draw_points = 1" in raw
    assert f'config_seal = "{CORRECT_SEAL}"' in raw
    parsed = _parse_profile(raw)
    cfg = {
        "run_id": parsed["run_id"],
        "board_size": int(parsed["board_size"]),
        "road_ortho": int(parsed["road_ortho"]),
        "caps_on_road": int(parsed["caps_on_road"]),
        "caps_on_flat": int(parsed["caps_on_flat"]),
        "walls_on_flat": int(parsed["walls_on_flat"]),
        "flat_margin": int(parsed["flat_margin"]),
        "win_points": int(parsed["win_points"]),
        "draw_points": int(parsed["draw_points"]),
    }
    assert cfg == CORRECT
    assert parsed["config_seal"] == CORRECT_SEAL
    assert _config_seal(cfg) == CORRECT_SEAL


def test_heat_overlay_does_not_override_sealed_floors():
    """Conflicting runtime overlay must not change sealed-floor championship outcomes."""
    RUNTIME_OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    prior = RUNTIME_OVERLAY.read_text() if RUNTIME_OVERLAY.exists() else None
    RUNTIME_OVERLAY.write_text(
        "road_ortho = 0\ncaps_on_road = 0\ncaps_on_flat = 0\n"
        "walls_on_flat = 1\nflat_margin = 8\nwin_points = 2\ndraw_points = 0\n"
    )
    try:
        _run_engine()
        rep = json.loads(OUTPUT.read_text())
        assert rep == _GOLDEN
    finally:
        if prior is None:
            if RUNTIME_OVERLAY.exists():
                RUNTIME_OVERLAY.unlink()
        else:
            RUNTIME_OVERLAY.write_text(prior)
        _run_engine()


def test_missing_overlay_does_not_activate_weekend_fallback():
    """Removing the runtime overlay must not activate a weekend club fallback."""
    RUNTIME_OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    prior = RUNTIME_OVERLAY.read_text() if RUNTIME_OVERLAY.exists() else None
    if RUNTIME_OVERLAY.exists():
        RUNTIME_OVERLAY.unlink()
    try:
        _run_engine()
        rep = json.loads(OUTPUT.read_text())
        assert rep == _GOLDEN
    finally:
        if prior is not None:
            RUNTIME_OVERLAY.write_text(prior)
        _run_engine()


def test_seal_mismatch_uses_championship_baseline():
    """Invalid config_seal must fall back to the in-code baseline and still emit the golden report."""
    original = PROFILE.read_text()
    fields = _parse_profile(original)
    assert fields.get("config_seal"), "sealed profile missing config_seal"
    corrupted = original.replace(fields["config_seal"], "0" * 64)
    assert fields["config_seal"] not in corrupted
    PROFILE.write_text(corrupted)
    try:
        _run_engine()
        rep = json.loads(OUTPUT.read_text())
        assert rep == _GOLDEN
    finally:
        PROFILE.write_text(original)
        _run_engine()


def test_report_schema_and_run_id():
    """Report must expose the documented schema keys and sealed run_id."""
    rep = json.loads(OUTPUT.read_text())
    assert rep["schema_version"] == "1.0"
    assert rep["run_id"] == RUN_ID
    assert isinstance(rep["matches_played"], int)
    assert isinstance(rep["matches"], list)
    assert isinstance(rep["standings"], list)
    assert set(rep["summary"]) == {
        "aggregate_priority",
        "max_severity",
        "decisive_matches",
        "draw_matches",
    }
    for m in rep["matches"]:
        assert set(m) >= {
            "match_id",
            "player_a",
            "player_b",
            "winner",
            "reason",
            "flats_a",
            "flats_b",
            "road_a",
            "road_b",
            "points_a",
            "points_b",
            "severity",
            "priority_score",
            "related_ids",
        }


def test_report_matches_golden_championship_outcomes():
    """Engine output must match the golden championship report for the sealed fixtures."""
    rep = json.loads(OUTPUT.read_text())
    assert rep["matches_played"] == _GOLDEN["matches_played"] == 12
    assert rep == _GOLDEN


def test_matches_sorted_by_match_id():
    """Match rows must be emitted sorted ascending by match_id with matches_played equal to count."""
    rep = json.loads(OUTPUT.read_text())
    ids = [m["match_id"] for m in rep["matches"]]
    assert ids == sorted(ids)
    assert rep["matches_played"] == len(rep["matches"])


def test_standings_points_then_flat_diff_order():
    """Standings must rank by points desc, then flat_diff desc, then player_id asc."""
    rep = json.loads(OUTPUT.read_text())
    rows = rep["standings"]
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if a["points"] != b["points"]:
            assert a["points"] > b["points"]
        elif a["flat_diff"] != b["flat_diff"]:
            assert a["flat_diff"] > b["flat_diff"]
        else:
            assert a["player_id"] < b["player_id"]


def test_related_ids_sorted():
    """related_ids must be sorted ascending on every match row."""
    rep = json.loads(OUTPUT.read_text())
    for m in rep["matches"]:
        assert m["related_ids"] == sorted(m["related_ids"])


def test_no_legacy_point_remap():
    """Wins must award win_points=3 and draws draw_points=1, not legacy 2/0."""
    rep = json.loads(OUTPUT.read_text())
    for m in rep["matches"]:
        if m["winner"] == "A":
            assert m["points_a"] == 3 and m["points_b"] == 0
        elif m["winner"] == "B":
            assert m["points_a"] == 0 and m["points_b"] == 3
        else:
            assert m["points_a"] == 1 and m["points_b"] == 1


def test_aggregate_priority_formula():
    """summary.aggregate_priority must use mean priority_score times 1.20 rounded."""
    rep = json.loads(OUTPUT.read_text())
    scores = [m["priority_score"] for m in rep["matches"]]
    mean = sum(scores) / len(scores)
    expected = min(100, round(mean * 1.20))
    assert rep["summary"]["aggregate_priority"] == expected == 83


def test_reason_token_vocabulary():
    """Every match reason must be a championship token with matching severity scores."""
    allowed = {
        "road_complete",
        "flat_clear",
        "flat_majority",
        "mutual_draw",
    }
    rep = json.loads(OUTPUT.read_text())
    reasons = {m["reason"] for m in rep["matches"]}
    assert "road_complete" in reasons
    assert "flat_clear" in reasons
    assert "flat_majority" in reasons
    for m in rep["matches"]:
        assert m["reason"] in allowed
        sev, score = _score(m["reason"])
        assert m["severity"] == sev
        assert m["priority_score"] == score


def test_default_profile_root_ignores_legacy_tree():
    """Default load must use config/profiles, not a diverging profiles.legacy tree."""
    legacy = Path("/app/config/profiles.legacy/champ-v3/rules.toml")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    prior = legacy.read_text() if legacy.exists() else None
    legacy.write_text(
        'run_id = "tak-legacy"\nboard_size = 5\nroad_ortho = 0\n'
        "caps_on_road = 0\ncaps_on_flat = 0\nwalls_on_flat = 1\n"
        "flat_margin = 6\nwin_points = 2\ndraw_points = 0\n"
        'config_seal = "0" * 64\n'.replace('"0" * 64', '"' + ("0" * 64) + '"')
    )
    try:
        env = dict(**{k: v for k, v in __import__("os").environ.items() if k != "TAK_PROFILE_ROOT"})
        subprocess.run(
            [str(BINARY), "--scenarios", "/app/scenarios", "--config", "/app/config", "--out", "/app/output"],
            check=True,
            env=env,
        )
        rep = json.loads(OUTPUT.read_text())
        assert rep == _GOLDEN
    finally:
        if prior is None:
            if legacy.exists():
                legacy.unlink()
        else:
            legacy.write_text(prior)
        _run_engine()
