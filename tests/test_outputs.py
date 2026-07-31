"""Validate the Moonrail table scorer against public and generated matches."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

APP = Path("/app")
SCORER = APP / "bin" / "moonrail-route"
PUBLIC_MATCH = APP / "task_file" / "samples" / "public_match.json"
RULES = APP / "task_file" / "moonrail_rules.md"
OUT_DIR = APP / "out"

PUBLIC_SHA256 = "23b687e6a747ceba520edefd98c41497154b69ab2b944f11aa1fe8d532475f94"
RULES_SHA256 = "7abf0bc5cb2c4b878f935e4a752ceca10e3f6d21b5352db491f24ca3069655f9"


def sha256(path: Path) -> str:
    """Return the SHA-256 digest for a task input file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def has_all(emblems: Counter[str], required: list[str] | None) -> bool:
    """Check whether all required emblems are present in the current multiset."""
    needed = Counter(required or [])
    return all(emblems[item] >= count for item, count in needed.items())


def site_map(match: dict) -> dict:
    """Return sites keyed by id."""
    return {site["id"]: site for site in match["sites"]}


def route_satisfied(path: list[str], route: list[str] | None) -> bool:
    """Return whether the route appears as a subsequence of the path."""
    needed = list(route or [])
    if not needed:
        return True
    pos = 0
    for site_id in path:
        if site_id == needed[pos]:
            pos += 1
            if pos == len(needed):
                return True
    return False


def contract_ids(match: dict, emblems: Counter[str], path: list[str], claimed: list[str], final_energy: int, final_heat: int) -> list[str]:
    """Return the best compatible completed contract id subset."""
    eligible = []
    for contract in match["contracts"]:
        forbids_absent = all(emblems[item] == 0 for item in contract.get("forbids", []))
        heat_ok = "final_heat_at_most" not in contract or final_heat <= contract["final_heat_at_most"]
        energy_ok = "final_energy_at_least" not in contract or final_energy >= contract["final_energy_at_least"]
        if (
            has_all(emblems, contract.get("requires", []))
            and forbids_absent
            and heat_ok
            and energy_ok
            and route_satisfied(path, contract.get("route", []))
            and route_satisfied(claimed, contract.get("claimed_order", []))
        ):
            eligible.append(contract)

    def conflicts(left: dict, right: dict) -> bool:
        return right["id"] in left.get("exclusive_with", []) or left["id"] in right.get("exclusive_with", [])

    best_ids: list[str] = []
    best_points = -1
    for mask in range(1 << len(eligible)):
        chosen = [eligible[i] for i in range(len(eligible)) if mask & (1 << i)]
        if any(conflicts(chosen[i], chosen[j]) for i in range(len(chosen)) for j in range(i + 1, len(chosen))):
            continue
        ids = sorted(contract["id"] for contract in chosen)
        points = sum(contract["points"] for contract in chosen)
        if points > best_points or (points == best_points and ",".join(ids) < ",".join(best_ids)):
            best_points = points
            best_ids = ids
    return best_ids


def echo_points(match: dict, path: list[str], claimed: list[str]) -> int:
    """Return final echo points for claimed sites revisited in the path."""
    sites = site_map(match)
    visits = Counter(path)
    return sum(sites[site_id].get("echo_points", 0) for site_id in claimed if visits[site_id] >= 2)


def result_key(result: dict) -> tuple:
    """Return the comparison key used after score has been maximized."""
    return (
        -result["score"],
        result["final_heat"],
        -result["final_energy"],
        len(result["path"]),
        ">".join(result["path"]),
        ",".join(result["contracts"]),
    )


def better(candidate: dict, incumbent: dict | None) -> bool:
    """Return whether candidate is the canonical best result so far."""
    if incumbent is None:
        return True
    return result_key(candidate) < result_key(incumbent)


def expected_result(match: dict) -> dict:
    """Evaluate every legal stopped plan and return the canonical best result."""
    sites = site_map(match)
    links_by_from: dict[str, list[dict]] = {}
    for link in match["links"]:
        links_by_from.setdefault(link["from"], []).append(link)

    start = match["start"]
    any_move = False
    best: dict | None = None

    def finish(path: list[str], claimed: list[str], emblems: Counter[str], score: int, energy: int, heat: int) -> None:
        nonlocal best
        contracts = contract_ids(match, emblems, path, claimed, energy, heat)
        total = score + echo_points(match, path, claimed) + sum(c["points"] for c in match["contracts"] if c["id"] in contracts)
        candidate = {
            "score": total,
            "path": path[:],
            "claimed": claimed[:],
            "contracts": contracts,
            "final_energy": energy,
            "final_heat": heat,
        }
        if better(candidate, best):
            best = candidate

    def walk(
        round_no: int,
        current: str,
        path: list[str],
        claimed: list[str],
        emblems: Counter[str],
        link_counts: Counter[str],
        score: int,
        energy: int,
        heat: int,
    ) -> None:
        nonlocal any_move
        finish(path, claimed, emblems, score, energy, heat)
        if round_no > match["round_limit"]:
            return
        for link in links_by_from.get(current, []):
            if not has_all(emblems, link.get("requires", [])):
                continue
            if "quiet_max_heat" in link and heat > link["quiet_max_heat"]:
                continue
            if "open_rounds" in link and round_no not in link["open_rounds"]:
                continue
            effective_cost = link["cost"] + link_counts[link["id"]]
            if energy < effective_cost:
                continue
            if not has_all(emblems, link.get("consumes", [])):
                continue
            revisit_heat = 1 if link["to"] in path and not link.get("safe_revisit", False) else 0
            next_heat = heat + link["heat"] + revisit_heat
            if next_heat > match["heat_limit"]:
                continue
            any_move = True
            next_energy = energy - effective_cost
            next_path = [*path, link["to"]]
            next_claimed = claimed[:]
            next_emblems = Counter(emblems)
            next_emblems.subtract(Counter(link.get("consumes", [])))
            next_emblems += Counter()
            next_link_counts = Counter(link_counts)
            next_link_counts[link["id"]] += 1
            next_score = score
            dest = sites[link["to"]]
            blocked = round_no in dest.get("block_rounds", [])
            already_claimed = link["to"] in next_claimed
            sealed = not has_all(next_emblems, dest.get("seal", []))
            if link["to"] != start and not already_claimed and not blocked and not sealed:
                next_claimed.append(link["to"])
                next_emblems[dest["emblem"]] += 1
                site_points = dest["points"]
                if "late_penalty" in dest and round_no > dest["late_penalty"]["after"]:
                    site_points = max(0, site_points - dest["late_penalty"]["points"])
                if "chain_points" in dest and dest["chain_points"]["after"] in claimed:
                    site_points += dest["chain_points"]["points"]
                next_score += site_points
                next_energy = min(match["energy_cap"], next_energy + dest["rest"])
            bonus = link.get("bonus", {})
            if "energy" in bonus:
                next_energy = min(match["energy_cap"], next_energy + bonus["energy"])
            if "emblem" in bonus:
                next_emblems[bonus["emblem"]] += 1
            walk(round_no + 1, link["to"], next_path, next_claimed, next_emblems, next_link_counts, next_score, next_energy, next_heat)

    walk(1, start, [start], [], Counter(), Counter(), 0, match["energy"], match["heat"])
    assert best is not None
    if not any_move and best["score"] == 0 and not best["contracts"]:
        return {
            "score": None,
            "path": [start],
            "claimed": [],
            "contracts": [],
            "final_energy": match["energy"],
            "final_heat": match["heat"],
        }
    return best


def run_scorer(input_path: Path, output_path: Path) -> dict:
    """Run the submitted scorer and return its JSON output."""
    output_path.unlink(missing_ok=True)
    completed = subprocess.run(
        ["node", str(SCORER), "--input", str(input_path), "--output", str(output_path)],
        cwd=APP,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert output_path.exists(), "scorer did not create the requested output file"
    return json.loads(output_path.read_text(encoding="utf-8"))


def assert_schema(result: dict) -> None:
    """Verify the output JSON uses the exact required schema."""
    assert list(result.keys()) == ["score", "path", "claimed", "contracts", "final_energy", "final_heat"]
    assert result["score"] is None or isinstance(result["score"], int)
    assert isinstance(result["path"], list) and all(isinstance(item, str) for item in result["path"])
    assert isinstance(result["claimed"], list) and all(isinstance(item, str) for item in result["claimed"])
    assert isinstance(result["contracts"], list) and all(isinstance(item, str) for item in result["contracts"])
    assert isinstance(result["final_energy"], int)
    assert isinstance(result["final_heat"], int)


def make_case(index: int, quiet: int, block_round: int, cap: int, heat_limit: int, bonus_emblem: str | None, consume_mode: int) -> dict:
    """Build a compatible Moonrail match variant from the verifier matrix."""
    suffix = f"{index:02d}"
    bonus = {"energy": 1}
    if bonus_emblem:
        bonus["emblem"] = bonus_emblem
    thorn_link = {"id": "c", "from": f"amber_{suffix}", "to": f"thorn_{suffix}", "cost": 3, "heat": 2, "quiet_max_heat": quiet}
    mirror_link = {"id": "d", "from": f"amber_{suffix}", "to": f"mirror_{suffix}", "cost": 2, "heat": 0, "bonus": bonus}
    basin_back = {"id": "k", "from": f"basin_{suffix}", "to": f"amber_{suffix}", "cost": 2, "heat": 1}
    basin_mirror = {"id": "l", "from": f"basin_{suffix}", "to": f"mirror_{suffix}", "cost": 1, "heat": 2}
    ivory_link = {"id": "m", "from": f"vane_{suffix}", "to": f"ivory_{suffix}", "cost": 2, "heat": 1, "requires": ["loom"]}
    crown_from_thorn = {"id": "i", "from": f"thorn_{suffix}", "to": f"crown_{suffix}", "cost": 2, "heat": 2, "requires": ["ivory"]}
    crown_from_ivory = {"id": "j", "from": f"ivory_{suffix}", "to": f"crown_{suffix}", "cost": 2, "heat": 2, "requires": ["thorn"]}
    if consume_mode == 1:
        thorn_link["consumes"] = ["amber"]
    elif consume_mode == 2:
        ivory_link["consumes"] = ["loom"]
    elif consume_mode == 3:
        crown_from_ivory["consumes"] = ["thorn"]
    if index % 2 == 1:
        basin_back["safe_revisit"] = True
    if index % 5 == 0:
        mirror_link["safe_revisit"] = True

    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 8 + (index % 3),
        "energy": 6 + (index % 2),
        "energy_cap": cap,
        "heat": index % 3,
        "heat_limit": heat_limit,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"amber_{suffix}", "emblem": "amber", "points": 4 + index % 4, "rest": 1},
            {"id": f"loom_{suffix}", "emblem": "loom", "points": 6, "rest": 0, "block_rounds": [block_round]},
            {"id": f"mirror_{suffix}", "emblem": "mirror", "points": 5, "rest": 2, "echo_points": 2 + index % 3},
            {"id": f"thorn_{suffix}", "emblem": "thorn", "points": 9, "rest": 0, "seal": ["amber"], "late_penalty": {"after": 3 + index % 3, "points": 4}},
            {"id": f"ivory_{suffix}", "emblem": "ivory", "points": 7, "rest": 1, "seal": ["loom"], "late_penalty": {"after": 5, "points": 2 + index % 2}},
            {"id": f"vane_{suffix}", "emblem": "vane", "points": 3 + (index % 5), "rest": 3},
            {"id": f"crown_{suffix}", "emblem": "crown", "points": 11, "rest": 0, "seal": ["thorn", "ivory"], "chain_points": {"after": f"basin_{suffix}", "points": 4 + index % 3}},
            {"id": f"basin_{suffix}", "emblem": "basin", "points": 4, "rest": 4, "echo_points": 3},
        ],
        "links": [
            {"id": "a", "from": f"gate_{suffix}", "to": f"amber_{suffix}", "cost": 2, "heat": 1},
            {"id": "b", "from": f"gate_{suffix}", "to": f"loom_{suffix}", "cost": 1, "heat": 2},
            thorn_link,
            mirror_link,
            {"id": "e", "from": f"loom_{suffix}", "to": f"ivory_{suffix}", "cost": 3, "heat": 1, "open_rounds": [2, 3, 4, 5, 7 + index % 3]},
            {"id": "f", "from": f"loom_{suffix}", "to": f"basin_{suffix}", "cost": 2, "heat": -1},
            {"id": "g", "from": f"mirror_{suffix}", "to": f"loom_{suffix}", "cost": 2, "heat": 1},
            {"id": "h", "from": f"mirror_{suffix}", "to": f"vane_{suffix}", "cost": 3, "heat": -1, "open_rounds": [3, 4, 5, 6, 8]},
            crown_from_thorn,
            crown_from_ivory,
            basin_back,
            basin_mirror,
            ivory_link,
            {"id": "n", "from": f"crown_{suffix}", "to": f"gate_{suffix}", "cost": 3, "heat": -3},
            {"id": "o", "from": f"vane_{suffix}", "to": f"basin_{suffix}", "cost": 1, "heat": 1},
        ],
        "contracts": [
            {
                "id": "arch",
                "requires": ["amber", "thorn", "crown"],
                "points": 12 + index % 3,
                "claimed_order": [f"amber_{suffix}", f"thorn_{suffix}", f"crown_{suffix}"] if index % 2 == 0 else [],
                "exclusive_with": ["full_court"] if index % 2 == 0 else [],
            },
            {
                "id": "weave",
                "requires": ["loom", "ivory", "mirror"],
                "points": 10,
                "route": [f"mirror_{suffix}", f"loom_{suffix}", f"ivory_{suffix}"] if index % 2 == 0 else [],
                "exclusive_with": ["lowline"] if index % 3 == 0 else [],
            },
            {"id": "lowline", "requires": ["basin", "vane"], "points": 6 + index % 4, "route": [f"basin_{suffix}", f"vane_{suffix}"]},
            {
                "id": "full_court",
                "requires": ["amber", "loom", "thorn", "ivory"],
                "points": 13 + index % 2,
                "claimed_order": [f"loom_{suffix}", f"ivory_{suffix}"] if index % 3 == 1 else [],
                "final_heat_at_most": 5 + index % 4,
            },
            {
                "id": "double_amber",
                "requires": ["amber", "amber"],
                "points": 8 + index % 3,
                "forbids": ["crown"] if index % 2 == 1 else [],
                "final_energy_at_least": 2 + index % 4,
                "exclusive_with": ["arch"],
            },
        ],
    }


def generated_cases() -> list[dict]:
    """Return the deterministic hidden-style compatibility matrix."""
    cases = []
    quiet_values = [2, 3, 4, 5]
    block_rounds = [1, 2, 3, 5]
    caps = [7, 8, 9, 10]
    limits = [6, 7, 8, 9]
    bonuses = [None, "loom", "ivory", "thorn", "amber"]
    for index in range(25):
        cases.append(make_case(index, quiet_values[index % 4], block_rounds[(index // 2) % 4], caps[(index // 3) % 4], limits[(index // 5) % 4], bonuses[index % 5], index % 4))
    return cases


def make_gauntlet_case(index: int) -> dict:
    """Build a dense variant where bonus, consume, seal, revisit, and contract gates collide."""
    suffix = f"g{index:02d}"
    heat_start = index % 3
    safe_return = index % 2 == 0
    bonus_item = ["key", "orb", "crown", "tide"][index % 4]
    block = [2 + (index % 3)]
    consume = ["orb"] if index % 4 in (1, 3) else []
    quiet_gate = 2 + (index % 4)
    round_limit = 8 + (index % 3)
    return {
        "version": "crescent-1",
        "start": f"dock_{suffix}",
        "round_limit": round_limit,
        "energy": 7 + (index % 3),
        "energy_cap": 10 + (index % 2),
        "heat": heat_start,
        "heat_limit": 7 + (index % 4),
        "sites": [
            {"id": f"dock_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"key_{suffix}", "emblem": "key", "points": 4, "rest": 1, "echo_points": 2},
            {"id": f"orb_{suffix}", "emblem": "orb", "points": 6, "rest": 1, "seal": ["key"], "block_rounds": block},
            {"id": f"tide_{suffix}", "emblem": "tide", "points": 5 + (index % 3), "rest": 3, "echo_points": 3},
            {"id": f"vault_{suffix}", "emblem": "vault", "points": 10, "rest": 0, "seal": ["orb"], "late_penalty": {"after": 4, "points": 6}},
            {"id": f"crown_{suffix}", "emblem": "crown", "points": 9, "rest": 0, "seal": ["vault", "tide"], "chain_points": {"after": f"key_{suffix}", "points": 5}},
            {"id": f"loop_{suffix}", "emblem": "loop", "points": 3, "rest": 4, "echo_points": 5},
            {"id": f"shade_{suffix}", "emblem": "shade", "points": 8, "rest": 0, "seal": [bonus_item], "late_penalty": {"after": 5, "points": 3}},
        ],
        "links": [
            {"id": "dk", "from": f"dock_{suffix}", "to": f"key_{suffix}", "cost": 1, "heat": 1},
            {"id": "dt", "from": f"dock_{suffix}", "to": f"tide_{suffix}", "cost": 2, "heat": 0, "bonus": {"emblem": "key", "energy": 1}},
            {"id": "ko", "from": f"key_{suffix}", "to": f"orb_{suffix}", "cost": 2, "heat": 1, "requires": ["key"], "open_rounds": [2, 3, 4]},
            {"id": "kt", "from": f"key_{suffix}", "to": f"tide_{suffix}", "cost": 1, "heat": 1, "bonus": {"emblem": bonus_item}},
            {"id": "tl", "from": f"tide_{suffix}", "to": f"loop_{suffix}", "cost": 1, "heat": -1, "safe_revisit": safe_return, "bonus": {"energy": 1}},
            {"id": "lk", "from": f"loop_{suffix}", "to": f"key_{suffix}", "cost": 1, "heat": 1, "safe_revisit": True},
            {"id": "lo", "from": f"loop_{suffix}", "to": f"orb_{suffix}", "cost": 2, "heat": 1, "requires": ["key"], "bonus": {"emblem": "orb"}},
            {"id": "ov", "from": f"orb_{suffix}", "to": f"vault_{suffix}", "cost": 2, "heat": 2, "requires": ["orb"], "consumes": consume},
            {"id": "vs", "from": f"vault_{suffix}", "to": f"shade_{suffix}", "cost": 1, "heat": 1, "requires": ["vault"], "quiet_max_heat": quiet_gate},
            {"id": "vc", "from": f"vault_{suffix}", "to": f"crown_{suffix}", "cost": 2, "heat": 2, "requires": ["vault", "tide"]},
            {"id": "sv", "from": f"shade_{suffix}", "to": f"vault_{suffix}", "cost": 1, "heat": 1},
            {"id": "sd", "from": f"shade_{suffix}", "to": f"dock_{suffix}", "cost": 2, "heat": -2},
            {"id": "cd", "from": f"crown_{suffix}", "to": f"dock_{suffix}", "cost": 2, "heat": -3},
            {"id": "to", "from": f"tide_{suffix}", "to": f"orb_{suffix}", "cost": 3, "heat": 2, "requires": ["key"], "open_rounds": [3, 4, 5, 6]},
        ],
        "contracts": [
            {
                "id": "crown_order",
                "requires": ["key", "orb", "vault", "crown"],
                "points": 16 + (index % 2),
                "claimed_order": [f"key_{suffix}", f"orb_{suffix}", f"vault_{suffix}", f"crown_{suffix}"],
                "exclusive_with": ["shade_loop"],
            },
            {
                "id": "shade_loop",
                "requires": [bonus_item, "shade", "vault"],
                "points": 15 + (index % 3),
                "route": [f"tide_{suffix}", f"loop_{suffix}", f"key_{suffix}", f"orb_{suffix}", f"vault_{suffix}", f"shade_{suffix}"],
            },
            {
                "id": "double_key",
                "requires": ["key", "key"],
                "points": 8 + (index % 4),
                "forbids": ["crown"] if index % 2 else [],
                "final_energy_at_least": 2 + (index % 3),
                "exclusive_with": ["crown_order"],
            },
            {
                "id": "cool_tail",
                "requires": ["tide", "loop"],
                "points": 7 + index % 2,
                "final_heat_at_most": 4 + (index % 3),
                "route": [f"tide_{suffix}", f"loop_{suffix}", f"key_{suffix}"],
            },
            {
                "id": "orb_spend",
                "requires": ["key", "vault"],
                "points": 9,
                "forbids": ["orb"] if consume else [],
                "claimed_order": [f"orb_{suffix}", f"vault_{suffix}"],
                "exclusive_with": ["shade_loop"] if index % 3 == 0 else [],
            },
        ],
    }


def generated_gauntlet_cases() -> list[dict]:
    """Return a harder deterministic matrix with dense rule interactions."""
    return [make_gauntlet_case(index) for index in range(14)]


def test_public_inputs_are_unchanged() -> None:
    """Verify the public match and visible rules were not edited to fit an answer."""
    assert sha256(PUBLIC_MATCH) == PUBLIC_SHA256
    assert sha256(RULES) == RULES_SHA256


def test_public_match_exact_result() -> None:
    """Verify the scorer returns the exact canonical result for the public match."""
    result = run_scorer(PUBLIC_MATCH, OUT_DIR / "result.json")
    assert_schema(result)
    assert result == expected_result(load_json(PUBLIC_MATCH))


def test_generated_compatibility_matrix() -> None:
    """Verify route selection across generated rule combinations and board shapes."""
    for idx, match in enumerate(generated_cases()):
        input_path = OUT_DIR / f"generated_{idx}.json"
        output_path = OUT_DIR / f"generated_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def test_generated_dense_gauntlet_matrix() -> None:
    """Verify harder generated boards with bonus, consume, seal, revisit, and final contract conflicts."""
    for idx, match in enumerate(generated_gauntlet_cases()):
        input_path = OUT_DIR / f"gauntlet_{idx}.json"
        output_path = OUT_DIR / f"gauntlet_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def test_no_legal_move_null_contract() -> None:
    """Verify null scoring when no move sequence can be legally taken."""
    match = {
        "version": "crescent-1",
        "start": "sealed_gate",
        "round_limit": 4,
        "energy": 1,
        "energy_cap": 5,
        "heat": 0,
        "heat_limit": 5,
        "sites": [
            {"id": "sealed_gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "far_lamp", "emblem": "lamp", "points": 8, "rest": 0},
        ],
        "links": [
            {"id": "blocked", "from": "sealed_gate", "to": "far_lamp", "cost": 2, "heat": 0}
        ],
        "contracts": [
            {"id": "lampwork", "requires": ["lamp"], "points": 5}
        ],
    }
    input_path = OUT_DIR / "null_case.json"
    output_path = OUT_DIR / "null_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_complete_result_tie_breaks() -> None:
    """Verify final-result tie-breaks are applied after full scoring, not per move."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 2,
        "energy": 4,
        "energy_cap": 5,
        "heat": 0,
        "heat_limit": 5,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "beta", "emblem": "b", "points": 5, "rest": 0},
            {"id": "alpha", "emblem": "a", "points": 5, "rest": 0},
            {"id": "omega", "emblem": "o", "points": 5, "rest": 1},
        ],
        "links": [
            {"id": "b", "from": "gate", "to": "beta", "cost": 1, "heat": 1},
            {"id": "a", "from": "gate", "to": "alpha", "cost": 1, "heat": 1},
            {"id": "bo", "from": "beta", "to": "omega", "cost": 1, "heat": 1},
            {"id": "ao", "from": "alpha", "to": "omega", "cost": 1, "heat": 1},
        ],
        "contracts": [],
    }
    input_path = OUT_DIR / "tie_case.json"
    output_path = OUT_DIR / "tie_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_consumption_before_arrival_and_contract_exclusion() -> None:
    """Verify consumed emblems affect arrival seals before final contract selection."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 5,
        "energy": 7,
        "energy_cap": 8,
        "heat": 0,
        "heat_limit": 8,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "amber", "emblem": "amber", "points": 4, "rest": 1},
            {"id": "forge", "emblem": "forge", "points": 5, "rest": 0, "seal": ["amber"]},
            {"id": "loom", "emblem": "loom", "points": 4, "rest": 2},
            {"id": "crown", "emblem": "crown", "points": 10, "rest": 0, "seal": ["forge"]},
        ],
        "links": [
            {"id": "ga", "from": "gate", "to": "amber", "cost": 1, "heat": 1},
            {"id": "af_bad", "from": "amber", "to": "forge", "cost": 1, "heat": 1, "requires": ["amber"], "consumes": ["amber"]},
            {"id": "al", "from": "amber", "to": "loom", "cost": 1, "heat": 1, "bonus": {"emblem": "amber"}},
            {"id": "lf", "from": "loom", "to": "forge", "cost": 2, "heat": 1, "requires": ["amber"]},
            {"id": "fc", "from": "forge", "to": "crown", "cost": 2, "heat": 2, "requires": ["forge"]},
        ],
        "contracts": [
            {"id": "crown_line", "requires": ["amber", "forge", "crown"], "points": 12, "exclusive_with": ["loom_line"]},
            {"id": "loom_line", "requires": ["amber", "loom", "forge"], "points": 12},
            {"id": "double_amber", "requires": ["amber", "amber"], "points": 5},
        ],
    }
    input_path = OUT_DIR / "consume_contract_case.json"
    output_path = OUT_DIR / "consume_contract_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_repeated_link_cost_and_revisit_heat() -> None:
    """Verify route history changes later link cost and heat on revisits."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 6,
        "energy": 8,
        "energy_cap": 9,
        "heat": 0,
        "heat_limit": 6,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "mill", "emblem": "mill", "points": 3, "rest": 3},
            {"id": "reed", "emblem": "reed", "points": 4, "rest": 1},
            {"id": "vault", "emblem": "vault", "points": 9, "rest": 0, "seal": ["reed"]},
            {"id": "spire", "emblem": "spire", "points": 8, "rest": 0, "seal": ["vault"]},
        ],
        "links": [
            {"id": "gm", "from": "gate", "to": "mill", "cost": 1, "heat": 1},
            {"id": "mr", "from": "mill", "to": "reed", "cost": 2, "heat": 1},
            {"id": "rm_safe", "from": "reed", "to": "mill", "cost": 1, "heat": 0, "safe_revisit": True, "bonus": {"energy": 1}},
            {"id": "mr", "from": "mill", "to": "reed", "cost": 2, "heat": 1},
            {"id": "rv", "from": "reed", "to": "vault", "cost": 2, "heat": 1},
            {"id": "vs", "from": "vault", "to": "spire", "cost": 2, "heat": 1, "requires": ["vault"]},
            {"id": "sg", "from": "spire", "to": "gate", "cost": 1, "heat": -2},
        ],
        "contracts": [
            {"id": "spire_line", "requires": ["reed", "vault", "spire"], "points": 13},
            {"id": "mill_loop", "requires": ["mill", "reed", "reed"], "points": 9},
        ],
    }
    input_path = OUT_DIR / "history_case.json"
    output_path = OUT_DIR / "history_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_echo_points_and_route_ordered_contracts() -> None:
    """Verify revisited claimed sites score echo points and contract routes are ordered subsequences."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 6,
        "energy": 8,
        "energy_cap": 9,
        "heat": 0,
        "heat_limit": 7,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "harp", "emblem": "harp", "points": 4, "rest": 2, "echo_points": 7},
            {"id": "ink", "emblem": "ink", "points": 6, "rest": 1},
            {"id": "quartz", "emblem": "quartz", "points": 6, "rest": 0, "seal": ["harp"]},
            {"id": "zinc", "emblem": "zinc", "points": 4, "rest": 1},
        ],
        "links": [
            {"id": "gh", "from": "gate", "to": "harp", "cost": 1, "heat": 1},
            {"id": "hi", "from": "harp", "to": "ink", "cost": 2, "heat": 1},
            {"id": "ih_safe", "from": "ink", "to": "harp", "cost": 1, "heat": 0, "safe_revisit": True},
            {"id": "hq", "from": "harp", "to": "quartz", "cost": 2, "heat": 1, "requires": ["harp"]},
            {"id": "qz", "from": "quartz", "to": "zinc", "cost": 1, "heat": 1},
            {"id": "iz", "from": "ink", "to": "zinc", "cost": 1, "heat": 2},
            {"id": "zq", "from": "zinc", "to": "quartz", "cost": 2, "heat": 1, "requires": ["harp"]},
        ],
        "contracts": [
            {"id": "right_order", "requires": ["harp", "ink", "quartz"], "points": 12, "route": ["harp", "ink", "harp", "quartz"]},
            {"id": "wrong_order", "requires": ["harp", "ink", "quartz"], "points": 16, "route": ["ink", "quartz", "harp"]},
            {"id": "zinc_tail", "requires": ["quartz", "zinc"], "points": 8, "exclusive_with": ["right_order"]},
        ],
    }
    input_path = OUT_DIR / "echo_route_case.json"
    output_path = OUT_DIR / "echo_route_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_open_rounds_and_late_claim_penalties() -> None:
    """Verify link windows and late claim penalties bind during route selection."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 6,
        "energy": 8,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 7,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "cairn", "emblem": "cairn", "points": 5, "rest": 2},
            {"id": "drum", "emblem": "drum", "points": 10, "rest": 0, "seal": ["cairn"], "late_penalty": {"after": 3, "points": 7}},
            {"id": "elm", "emblem": "elm", "points": 5, "rest": 2},
            {"id": "frost", "emblem": "frost", "points": 9, "rest": 0, "seal": ["drum"]},
        ],
        "links": [
            {"id": "gc", "from": "gate", "to": "cairn", "cost": 1, "heat": 1},
            {"id": "cd_fast", "from": "cairn", "to": "drum", "cost": 2, "heat": 1, "open_rounds": [2, 3]},
            {"id": "ce", "from": "cairn", "to": "elm", "cost": 1, "heat": 0},
            {"id": "ed_late", "from": "elm", "to": "drum", "cost": 1, "heat": 1, "open_rounds": [4, 5]},
            {"id": "df", "from": "drum", "to": "frost", "cost": 2, "heat": 2, "requires": ["drum"]},
            {"id": "fg", "from": "frost", "to": "gate", "cost": 1, "heat": -2},
        ],
        "contracts": [
            {"id": "fast_drum", "requires": ["cairn", "drum", "frost"], "points": 12, "route": ["cairn", "drum", "frost"]},
            {"id": "elm_detour", "requires": ["cairn", "elm", "drum"], "points": 11, "exclusive_with": ["fast_drum"]},
        ],
    }
    input_path = OUT_DIR / "timing_case.json"
    output_path = OUT_DIR / "timing_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_final_state_contract_gates() -> None:
    """Verify forbidden emblems and final resource gates affect contract eligibility."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 7,
        "energy": 8,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 8,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "salt", "emblem": "salt", "points": 4, "rest": 2},
            {"id": "iron", "emblem": "iron", "points": 5, "rest": 1},
            {"id": "ember", "emblem": "ember", "points": 6, "rest": 0, "seal": ["salt"]},
            {"id": "clear", "emblem": "clear", "points": 3, "rest": 3},
        ],
        "links": [
            {"id": "gs", "from": "gate", "to": "salt", "cost": 1, "heat": 1},
            {"id": "si", "from": "salt", "to": "iron", "cost": 1, "heat": 1},
            {"id": "ie", "from": "iron", "to": "ember", "cost": 2, "heat": 3, "requires": ["salt"]},
            {"id": "ic", "from": "iron", "to": "clear", "cost": 1, "heat": -1, "consumes": ["iron"], "bonus": {"energy": 1}},
            {"id": "ce", "from": "clear", "to": "ember", "cost": 2, "heat": 1, "requires": ["salt"]},
            {"id": "eg", "from": "ember", "to": "gate", "cost": 1, "heat": -2},
        ],
        "contracts": [
            {"id": "clean_salt", "requires": ["salt", "clear"], "forbids": ["iron"], "points": 13, "final_energy_at_least": 5},
            {"id": "hot_iron", "requires": ["salt", "iron", "ember"], "points": 14, "final_heat_at_most": 3},
            {"id": "ember_tail", "requires": ["salt", "ember"], "points": 9, "route": ["salt", "clear", "ember"]},
        ],
    }
    input_path = OUT_DIR / "final_gate_case.json"
    output_path = OUT_DIR / "final_gate_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_claim_order_and_chain_points() -> None:
    """Verify claim order differs from path order and chain points score only after prior claims."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 7,
        "energy": 9,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 8,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "blue", "emblem": "blue", "points": 4, "rest": 2},
            {"id": "red", "emblem": "red", "points": 6, "rest": 1, "seal": ["blue"]},
            {"id": "gold", "emblem": "gold", "points": 7, "rest": 0, "seal": ["red"], "chain_points": {"after": "blue", "points": 5}},
            {"id": "black", "emblem": "black", "points": 5, "rest": 2, "block_rounds": [2]},
        ],
        "links": [
            {"id": "gbad", "from": "gate", "to": "black", "cost": 1, "heat": 1},
            {"id": "bg", "from": "black", "to": "gate", "cost": 1, "heat": 0, "safe_revisit": True},
            {"id": "gblue", "from": "gate", "to": "blue", "cost": 1, "heat": 1},
            {"id": "br", "from": "blue", "to": "red", "cost": 2, "heat": 1},
            {"id": "rg", "from": "red", "to": "gold", "cost": 2, "heat": 2, "requires": ["red"]},
            {"id": "gb", "from": "gold", "to": "black", "cost": 1, "heat": 1},
        ],
        "contracts": [
            {"id": "claimed_chain", "requires": ["blue", "red", "gold"], "points": 14, "claimed_order": ["blue", "red", "gold"]},
            {"id": "path_only_trap", "requires": ["blue", "red", "black"], "points": 16, "route": ["black", "blue", "red"], "claimed_order": ["black", "blue"]},
        ],
    }
    input_path = OUT_DIR / "claim_order_case.json"
    output_path = OUT_DIR / "claim_order_case_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def make_delayed_claim_case(index: int) -> dict:
    """Build a variant where early path visits must not prevent later first claims."""
    suffix = f"d{index:02d}"
    first_block = 2 + (index % 2)
    heat_limit = 8 + (index % 3)
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 9,
        "energy": 8 + (index % 2),
        "energy_cap": 11,
        "heat": index % 2,
        "heat_limit": heat_limit,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"locked_{suffix}", "emblem": "locked", "points": 11, "rest": 0, "seal": ["key"], "echo_points": 4},
            {"id": f"key_{suffix}", "emblem": "key", "points": 4, "rest": 3},
            {"id": f"blocked_{suffix}", "emblem": "blocked", "points": 9, "rest": 1, "block_rounds": [first_block], "chain_points": {"after": f"key_{suffix}", "points": 5}},
            {"id": f"relay_{suffix}", "emblem": "relay", "points": 3, "rest": 4, "echo_points": 2},
            {"id": f"final_{suffix}", "emblem": "final", "points": 12, "rest": 0, "seal": ["locked", "blocked"]},
        ],
        "links": [
            {"id": "gl", "from": f"gate_{suffix}", "to": f"locked_{suffix}", "cost": 1, "heat": 1},
            {"id": "lk", "from": f"locked_{suffix}", "to": f"key_{suffix}", "cost": 1, "heat": 1, "bonus": {"energy": 1}},
            {"id": "kb", "from": f"key_{suffix}", "to": f"blocked_{suffix}", "cost": 2, "heat": 1},
            {"id": "br", "from": f"blocked_{suffix}", "to": f"relay_{suffix}", "cost": 1, "heat": -1, "safe_revisit": index % 2 == 0},
            {"id": "rl", "from": f"relay_{suffix}", "to": f"locked_{suffix}", "cost": 2, "heat": 1, "requires": ["key"], "bonus": {"emblem": "key"}},
            {"id": "lb", "from": f"locked_{suffix}", "to": f"blocked_{suffix}", "cost": 1, "heat": 1, "requires": ["locked"]},
            {"id": "bf", "from": f"blocked_{suffix}", "to": f"final_{suffix}", "cost": 2, "heat": 2, "requires": ["locked", "blocked"]},
            {"id": "fg", "from": f"final_{suffix}", "to": f"gate_{suffix}", "cost": 2, "heat": -2},
        ],
        "contracts": [
            {
                "id": "late_unlock",
                "requires": ["key", "locked", "blocked", "final"],
                "points": 18 + (index % 3),
                "claimed_order": [f"key_{suffix}", f"locked_{suffix}", f"blocked_{suffix}", f"final_{suffix}"],
            },
            {
                "id": "path_memory_trap",
                "requires": ["key", "locked"],
                "points": 10,
                "route": [f"locked_{suffix}", f"key_{suffix}", f"blocked_{suffix}", f"relay_{suffix}", f"locked_{suffix}"],
                "exclusive_with": ["late_unlock"] if index % 2 else [],
            },
            {
                "id": "cool_finish",
                "requires": ["relay", "final"],
                "points": 7,
                "final_heat_at_most": heat_limit - 1,
            },
        ],
    }


def delayed_claim_cases() -> list[dict]:
    """Return delayed-claim variants where path membership and claim membership diverge."""
    return [make_delayed_claim_case(index) for index in range(10)]


def test_delayed_claim_generated_matrix() -> None:
    """Verify sealed or blocked prior visits can become first claims on later arrivals."""
    for idx, match in enumerate(delayed_claim_cases()):
        input_path = OUT_DIR / f"delayed_claim_{idx}.json"
        output_path = OUT_DIR / f"delayed_claim_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def test_contract_subset_lexicographic_pressure() -> None:
    """Verify final contract selection considers all eligible contracts before exclusivity tie-breaks."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 6,
        "energy": 8,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 7,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "a", "emblem": "a", "points": 3, "rest": 2},
            {"id": "b", "emblem": "b", "points": 3, "rest": 1},
            {"id": "c", "emblem": "c", "points": 3, "rest": 1},
            {"id": "d", "emblem": "d", "points": 3, "rest": 0, "seal": ["b"]},
            {"id": "e", "emblem": "e", "points": 3, "rest": 0, "seal": ["c"]},
        ],
        "links": [
            {"id": "ga", "from": "gate", "to": "a", "cost": 1, "heat": 1},
            {"id": "ab", "from": "a", "to": "b", "cost": 1, "heat": 1},
            {"id": "bc", "from": "b", "to": "c", "cost": 1, "heat": 1},
            {"id": "cd", "from": "c", "to": "d", "cost": 1, "heat": 1},
            {"id": "de", "from": "d", "to": "e", "cost": 1, "heat": 1},
            {"id": "eg", "from": "e", "to": "gate", "cost": 1, "heat": -2},
        ],
        "contracts": [
            {"id": "alpha", "requires": ["a", "b"], "points": 9, "exclusive_with": ["delta"]},
            {"id": "bravo", "requires": ["b", "c"], "points": 9, "exclusive_with": ["echo"]},
            {"id": "charlie", "requires": ["c", "d"], "points": 9},
            {"id": "delta", "requires": ["d", "e"], "points": 9, "exclusive_with": ["alpha"]},
            {"id": "echo", "requires": ["a", "e"], "points": 9, "exclusive_with": ["bravo"]},
            {"id": "single_big", "requires": ["a", "b", "c", "d", "e"], "points": 20, "exclusive_with": ["alpha", "bravo", "charlie", "delta", "echo"]},
        ],
    }
    input_path = OUT_DIR / "contract_subset_pressure.json"
    output_path = OUT_DIR / "contract_subset_pressure_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def make_multiset_pressure_case(index: int) -> dict:
    """Build a variant where repeated emblem counts are required, consumed, and restored by bonuses."""
    suffix = f"m{index:02d}"
    route_first = index % 2 == 0
    consume_pair = ["spark", "spark"] if index % 3 == 0 else ["spark"]
    return {
        "version": "crescent-1",
        "start": f"start_{suffix}",
        "round_limit": 8 + (index % 2),
        "energy": 8,
        "energy_cap": 11,
        "heat": index % 2,
        "heat_limit": 8,
        "sites": [
            {"id": f"start_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"spark_{suffix}", "emblem": "spark", "points": 4, "rest": 2, "echo_points": 2},
            {"id": f"lens_{suffix}", "emblem": "lens", "points": 5, "rest": 1, "seal": ["spark"]},
            {"id": f"mint_{suffix}", "emblem": "mint", "points": 2, "rest": 4, "block_rounds": [2]},
            {"id": f"forge_{suffix}", "emblem": "forge", "points": 11, "rest": 0, "seal": ["lens"]},
            {"id": f"seal_{suffix}", "emblem": "seal", "points": 8, "rest": 0, "seal": ["spark", "spark"]},
            {"id": f"coda_{suffix}", "emblem": "coda", "points": 9, "rest": 0, "seal": ["forge", "seal"]},
        ],
        "links": [
            {"id": "ss", "from": f"start_{suffix}", "to": f"spark_{suffix}", "cost": 1, "heat": 1},
            {"id": "sl", "from": f"spark_{suffix}", "to": f"lens_{suffix}", "cost": 1, "heat": 1, "requires": ["spark"]},
            {"id": "lm", "from": f"lens_{suffix}", "to": f"mint_{suffix}", "cost": 1, "heat": -1, "bonus": {"emblem": "spark", "energy": 1}},
            {"id": "ms", "from": f"mint_{suffix}", "to": f"spark_{suffix}", "cost": 1, "heat": 1, "safe_revisit": True, "bonus": {"emblem": "spark"}},
            {"id": "sf", "from": f"spark_{suffix}", "to": f"forge_{suffix}", "cost": 2, "heat": 2, "requires": ["spark", "spark"], "consumes": consume_pair},
            {"id": "fs", "from": f"forge_{suffix}", "to": f"seal_{suffix}", "cost": 1, "heat": 1, "requires": ["forge"], "bonus": {"emblem": "spark"}},
            {"id": "sc", "from": f"seal_{suffix}", "to": f"coda_{suffix}", "cost": 2, "heat": 2, "requires": ["seal", "spark"]},
            {"id": "cs", "from": f"coda_{suffix}", "to": f"start_{suffix}", "cost": 1, "heat": -2},
            {"id": "lf", "from": f"lens_{suffix}", "to": f"forge_{suffix}", "cost": 3, "heat": 1, "requires": ["spark"], "quiet_max_heat": 4 + (index % 3)},
        ],
        "contracts": [
            {
                "id": "double_spark",
                "requires": ["spark", "spark", "forge"],
                "points": 15,
                "claimed_order": [f"spark_{suffix}", f"lens_{suffix}", f"forge_{suffix}"] if route_first else [],
                "exclusive_with": ["spent_spark"],
            },
            {
                "id": "spent_spark",
                "requires": ["forge", "seal"],
                "forbids": ["spark"] if index % 3 == 0 else [],
                "points": 14 + (index % 2),
            },
            {
                "id": "full_coda",
                "requires": ["spark", "lens", "forge", "seal", "coda"],
                "points": 18,
                "route": [f"lens_{suffix}", f"mint_{suffix}", f"spark_{suffix}", f"forge_{suffix}", f"seal_{suffix}", f"coda_{suffix}"],
                "final_heat_at_most": 7,
            },
            {
                "id": "mint_echo",
                "requires": ["mint", "spark"],
                "points": 7,
                "route": [f"mint_{suffix}", f"spark_{suffix}", f"forge_{suffix}"],
            },
        ],
    }


def multiset_pressure_cases() -> list[dict]:
    """Return variants that require real emblem multiset accounting."""
    return [make_multiset_pressure_case(index) for index in range(12)]


def test_multiset_bonus_and_consume_generated_matrix() -> None:
    """Verify repeated emblem requirements, consumes, bonus emblems, and final forbids interact correctly."""
    for idx, match in enumerate(multiset_pressure_cases()):
        input_path = OUT_DIR / f"multiset_{idx}.json"
        output_path = OUT_DIR / f"multiset_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def test_blocked_site_does_not_grant_rest_or_emblem_before_later_claim() -> None:
    """Verify a blocked visit adds only path history, not points, rest, emblem, or claimed order."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 7,
        "energy": 6,
        "energy_cap": 9,
        "heat": 0,
        "heat_limit": 7,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "blocked", "emblem": "blocked", "points": 12, "rest": 5, "block_rounds": [1]},
            {"id": "key", "emblem": "key", "points": 4, "rest": 2},
            {"id": "vault", "emblem": "vault", "points": 9, "rest": 0, "seal": ["blocked"]},
        ],
        "links": [
            {"id": "gb", "from": "gate", "to": "blocked", "cost": 1, "heat": 1},
            {"id": "bk", "from": "blocked", "to": "key", "cost": 2, "heat": 1},
            {"id": "kg", "from": "key", "to": "gate", "cost": 1, "heat": -1},
            {"id": "gb", "from": "gate", "to": "blocked", "cost": 1, "heat": 1},
            {"id": "bv", "from": "blocked", "to": "vault", "cost": 2, "heat": 1, "requires": ["blocked"]},
        ],
        "contracts": [
            {"id": "delayed_block", "requires": ["blocked", "vault"], "points": 14, "claimed_order": ["blocked", "vault"]},
            {"id": "path_seen", "requires": ["key"], "points": 5, "route": ["blocked", "key", "gate", "blocked"]},
        ],
    }
    input_path = OUT_DIR / "blocked_no_reward_then_claim.json"
    output_path = OUT_DIR / "blocked_no_reward_then_claim_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def test_complete_tie_break_contract_string_after_route_and_resources() -> None:
    """Verify contract-id tie-break applies only after score, heat, energy, path length, and path string tie."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 3,
        "energy": 5,
        "energy_cap": 5,
        "heat": 0,
        "heat_limit": 5,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "a", "emblem": "a", "points": 3, "rest": 0},
            {"id": "b", "emblem": "b", "points": 3, "rest": 0},
            {"id": "c", "emblem": "c", "points": 3, "rest": 0},
        ],
        "links": [
            {"id": "ga", "from": "gate", "to": "a", "cost": 1, "heat": 1},
            {"id": "ab", "from": "a", "to": "b", "cost": 1, "heat": 1},
            {"id": "bc", "from": "b", "to": "c", "cost": 1, "heat": 1},
        ],
        "contracts": [
            {"id": "aa", "requires": ["a", "b"], "points": 5, "exclusive_with": ["zz"]},
            {"id": "mm", "requires": ["b", "c"], "points": 5},
            {"id": "zz", "requires": ["a", "c"], "points": 5, "exclusive_with": ["aa"]},
        ],
    }
    input_path = OUT_DIR / "contract_string_tie.json"
    output_path = OUT_DIR / "contract_string_tie_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def make_history_dominance_case(index: int) -> dict:
    """Build a board where path history and link use counts prevent shallow state merging."""
    suffix = f"h{index:02d}"
    safe = index % 2 == 0
    first_bonus = ["moon", "star", "key"][index % 3]
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 8,
        "energy": 7 + (index % 2),
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 8,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"moon_{suffix}", "emblem": "moon", "points": 4, "rest": 2, "echo_points": 4},
            {"id": f"star_{suffix}", "emblem": "star", "points": 5, "rest": 1, "seal": ["moon"]},
            {"id": f"hub_{suffix}", "emblem": "hub", "points": 3, "rest": 3, "echo_points": 3},
            {"id": f"key_{suffix}", "emblem": "key", "points": 6, "rest": 0, "seal": [first_bonus]},
            {"id": f"spire_{suffix}", "emblem": "spire", "points": 10, "rest": 0, "seal": ["star", "key"]},
            {"id": f"tail_{suffix}", "emblem": "tail", "points": 5, "rest": 2, "block_rounds": [5]},
        ],
        "links": [
            {"id": "gm", "from": f"gate_{suffix}", "to": f"moon_{suffix}", "cost": 1, "heat": 1},
            {"id": "gh", "from": f"gate_{suffix}", "to": f"hub_{suffix}", "cost": 1, "heat": 1, "bonus": {"emblem": first_bonus}},
            {"id": "mh", "from": f"moon_{suffix}", "to": f"hub_{suffix}", "cost": 1, "heat": 1, "bonus": {"energy": 1}},
            {"id": "hm", "from": f"hub_{suffix}", "to": f"moon_{suffix}", "cost": 1, "heat": 0, "safe_revisit": safe},
            {"id": "hs", "from": f"hub_{suffix}", "to": f"star_{suffix}", "cost": 2, "heat": 1, "requires": ["moon"]},
            {"id": "sh", "from": f"star_{suffix}", "to": f"hub_{suffix}", "cost": 1, "heat": -1, "safe_revisit": True, "bonus": {"emblem": "key"}},
            {"id": "hk", "from": f"hub_{suffix}", "to": f"key_{suffix}", "cost": 2, "heat": 1, "requires": [first_bonus]},
            {"id": "kh", "from": f"key_{suffix}", "to": f"hub_{suffix}", "cost": 1, "heat": 1},
            {"id": "hp", "from": f"hub_{suffix}", "to": f"spire_{suffix}", "cost": 2, "heat": 2, "requires": ["star", "key"]},
            {"id": "pt", "from": f"spire_{suffix}", "to": f"tail_{suffix}", "cost": 1, "heat": 1},
            {"id": "tg", "from": f"tail_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -2},
            {"id": "loop", "from": f"hub_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": 0, "safe_revisit": True},
            {"id": "loop", "from": f"gate_{suffix}", "to": f"hub_{suffix}", "cost": 1, "heat": 0, "safe_revisit": True},
        ],
        "contracts": [
            {
                "id": "moon_echo_route",
                "requires": ["moon", "hub", "star"],
                "points": 12,
                "route": [f"moon_{suffix}", f"hub_{suffix}", f"moon_{suffix}", f"hub_{suffix}", f"star_{suffix}"],
                "exclusive_with": ["short_spire"],
            },
            {
                "id": "short_spire",
                "requires": ["star", "key", "spire"],
                "points": 15 + index % 2,
                "claimed_order": [f"star_{suffix}", f"key_{suffix}", f"spire_{suffix}"],
            },
            {
                "id": "tail_after_spire",
                "requires": ["spire", "tail"],
                "points": 11,
                "claimed_order": [f"spire_{suffix}", f"tail_{suffix}"],
                "final_heat_at_most": 7,
            },
            {
                "id": "loop_memory",
                "requires": ["hub"],
                "points": 6,
                "route": [f"hub_{suffix}", f"gate_{suffix}", f"hub_{suffix}"],
                "exclusive_with": ["tail_after_spire"] if index % 3 == 0 else [],
            },
        ],
    }


def history_dominance_cases() -> list[dict]:
    """Return variants that punish pruning away path and link-count history."""
    return [make_history_dominance_case(index) for index in range(10)]


def test_history_sensitive_dominance_generated_matrix() -> None:
    """Verify equivalent-looking states still preserve route, echo, claimed order, and link-count history."""
    for idx, match in enumerate(history_dominance_cases()):
        input_path = OUT_DIR / f"history_dominance_{idx}.json"
        output_path = OUT_DIR / f"history_dominance_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def test_repeated_link_count_changes_later_legality_after_same_site_return() -> None:
    """Verify using the same link id on separate arcs raises only that id's later effective cost."""
    match = {
        "version": "crescent-1",
        "start": "gate",
        "round_limit": 7,
        "energy": 6,
        "energy_cap": 8,
        "heat": 0,
        "heat_limit": 7,
        "sites": [
            {"id": "gate", "emblem": "none", "points": 0, "rest": 0},
            {"id": "a", "emblem": "a", "points": 4, "rest": 2},
            {"id": "b", "emblem": "b", "points": 4, "rest": 2},
            {"id": "c", "emblem": "c", "points": 10, "rest": 0, "seal": ["a", "b"]},
            {"id": "d", "emblem": "d", "points": 7, "rest": 0, "seal": ["c"]},
        ],
        "links": [
            {"id": "x", "from": "gate", "to": "a", "cost": 1, "heat": 1},
            {"id": "ag", "from": "a", "to": "gate", "cost": 1, "heat": 0, "safe_revisit": True},
            {"id": "x", "from": "gate", "to": "b", "cost": 1, "heat": 1},
            {"id": "bc", "from": "b", "to": "c", "cost": 2, "heat": 2, "requires": ["a", "b"]},
            {"id": "cd", "from": "c", "to": "d", "cost": 2, "heat": 2, "requires": ["c"]},
        ],
        "contracts": [
            {"id": "two_x_path", "requires": ["a", "b", "c"], "points": 14, "route": ["a", "gate", "b", "c"]},
            {"id": "full_tail", "requires": ["a", "b", "c", "d"], "points": 13, "final_energy_at_least": 0},
        ],
    }
    input_path = OUT_DIR / "repeated_link_legality.json"
    output_path = OUT_DIR / "repeated_link_legality_result.json"
    input_path.write_text(json.dumps(match), encoding="utf-8")
    result = run_scorer(input_path, output_path)
    assert_schema(result)
    assert result == expected_result(match)


def make_contract_lattice_case(index: int) -> dict:
    """Build a board where the best final contract subset is not the best-looking local pair."""
    suffix = f"l{index:02d}"
    cool_route = index % 2 == 0
    forbid_tail = index % 3 == 0
    return {
        "version": "crescent-1",
        "start": f"start_{suffix}",
        "round_limit": 7,
        "energy": 7 + (index % 2),
        "energy_cap": 9,
        "heat": index % 2,
        "heat_limit": 7,
        "sites": [
            {"id": f"start_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"a_{suffix}", "emblem": "a", "points": 3, "rest": 2},
            {"id": f"b_{suffix}", "emblem": "b", "points": 3, "rest": 1},
            {"id": f"c_{suffix}", "emblem": "c", "points": 3, "rest": 1, "seal": ["a"]},
            {"id": f"d_{suffix}", "emblem": "d", "points": 3, "rest": 1, "seal": ["b"]},
            {"id": f"e_{suffix}", "emblem": "e", "points": 3, "rest": 0, "seal": ["c"]},
            {"id": f"f_{suffix}", "emblem": "f", "points": 3, "rest": 0, "seal": ["d"]},
            {"id": f"tail_{suffix}", "emblem": "tail", "points": 2, "rest": 0, "echo_points": 3},
        ],
        "links": [
            {"id": "sa", "from": f"start_{suffix}", "to": f"a_{suffix}", "cost": 1, "heat": 1},
            {"id": "ab", "from": f"a_{suffix}", "to": f"b_{suffix}", "cost": 1, "heat": 1},
            {"id": "bc", "from": f"b_{suffix}", "to": f"c_{suffix}", "cost": 1, "heat": 1},
            {"id": "cd", "from": f"c_{suffix}", "to": f"d_{suffix}", "cost": 1, "heat": 1},
            {"id": "de", "from": f"d_{suffix}", "to": f"e_{suffix}", "cost": 1, "heat": 1},
            {"id": "ef", "from": f"e_{suffix}", "to": f"f_{suffix}", "cost": 1, "heat": 1},
            {"id": "ft", "from": f"f_{suffix}", "to": f"tail_{suffix}", "cost": 1, "heat": -2 if cool_route else 0},
            {"id": "ts", "from": f"tail_{suffix}", "to": f"start_{suffix}", "cost": 1, "heat": -2, "safe_revisit": True},
            {"id": "st", "from": f"start_{suffix}", "to": f"tail_{suffix}", "cost": 2, "heat": 1, "bonus": {"emblem": "a"}},
            {"id": "tc", "from": f"tail_{suffix}", "to": f"c_{suffix}", "cost": 2, "heat": 1, "requires": ["a"]},
        ],
        "contracts": [
            {"id": "aa_big", "requires": ["a", "b", "c"], "points": 13, "exclusive_with": ["ab_mid", "ac_mid", "all_line"]},
            {"id": "ab_mid", "requires": ["b", "d"], "points": 9, "exclusive_with": ["aa_big", "bd_mid"]},
            {"id": "ac_mid", "requires": ["c", "e"], "points": 9, "exclusive_with": ["aa_big", "ce_mid"]},
            {"id": "bd_mid", "requires": ["d", "f"], "points": 9, "exclusive_with": ["ab_mid", "tail_lock"]},
            {"id": "ce_mid", "requires": ["a", "e", "f"], "points": 9, "exclusive_with": ["ac_mid"]},
            {"id": "tail_lock", "requires": ["tail", "f"], "points": 10, "forbids": ["tail"] if forbid_tail else [], "exclusive_with": ["bd_mid"]},
            {
                "id": "all_line",
                "requires": ["a", "b", "c", "d", "e", "f"],
                "points": 21,
                "route": [f"a_{suffix}", f"b_{suffix}", f"c_{suffix}", f"d_{suffix}", f"e_{suffix}", f"f_{suffix}"],
                "exclusive_with": ["aa_big", "ab_mid", "ac_mid"],
                "final_heat_at_most": 5 + (index % 2),
            },
            {
                "id": "ordered_tail",
                "requires": ["a", "tail"],
                "points": 6 + (index % 3),
                "claimed_order": [f"f_{suffix}", f"tail_{suffix}"] if cool_route else [],
            },
        ],
    }


def contract_lattice_cases() -> list[dict]:
    """Return variants with non-obvious final contract exclusivity optima."""
    return [make_contract_lattice_case(index) for index in range(10)]


def test_contract_lattice_generated_matrix() -> None:
    """Verify contract subset optimization compares all eligible exclusive combinations."""
    for idx, match in enumerate(contract_lattice_cases()):
        input_path = OUT_DIR / f"contract_lattice_{idx}.json"
        output_path = OUT_DIR / f"contract_lattice_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_low_local_high_final_case(index: int) -> dict:
    """Build a board where an early low-score stop unlocks better late final scoring."""
    suffix = f"q{index:02d}"
    first_block = 2 + (index % 2)
    key_bonus = "coin" if index % 3 == 0 else "mark"
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 8 + (index % 2),
        "energy": 7,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 7 + (index % 2),
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"coin_{suffix}", "emblem": "coin", "points": 9, "rest": 0, "late_penalty": {"after": 2, "points": 8}},
            {"id": f"mark_{suffix}", "emblem": "mark", "points": 2, "rest": 4, "echo_points": 4},
            {"id": f"lock_{suffix}", "emblem": "lock", "points": 3, "rest": 2, "seal": [key_bonus], "block_rounds": [first_block]},
            {"id": f"forge_{suffix}", "emblem": "forge", "points": 4, "rest": 1, "seal": ["lock"]},
            {"id": f"vault_{suffix}", "emblem": "vault", "points": 12, "rest": 0, "seal": ["forge"], "chain_points": {"after": f"mark_{suffix}", "points": 7}},
            {"id": f"cool_{suffix}", "emblem": "cool", "points": 1, "rest": 3, "echo_points": 5},
        ],
        "links": [
            {"id": "gc", "from": f"gate_{suffix}", "to": f"coin_{suffix}", "cost": 1, "heat": 1},
            {"id": "gm", "from": f"gate_{suffix}", "to": f"mark_{suffix}", "cost": 1, "heat": 1, "bonus": {"emblem": key_bonus}},
            {"id": "cm", "from": f"coin_{suffix}", "to": f"mark_{suffix}", "cost": 2, "heat": 1, "bonus": {"emblem": "mark"}},
            {"id": "ml", "from": f"mark_{suffix}", "to": f"lock_{suffix}", "cost": 2, "heat": 1, "requires": [key_bonus]},
            {"id": "lc", "from": f"lock_{suffix}", "to": f"cool_{suffix}", "cost": 1, "heat": -1, "safe_revisit": index % 2 == 0},
            {"id": "cl", "from": f"cool_{suffix}", "to": f"lock_{suffix}", "cost": 1, "heat": 1, "requires": [key_bonus], "bonus": {"energy": 1}},
            {"id": "lf", "from": f"lock_{suffix}", "to": f"forge_{suffix}", "cost": 2, "heat": 1, "requires": ["lock"]},
            {"id": "fv", "from": f"forge_{suffix}", "to": f"vault_{suffix}", "cost": 2, "heat": 2, "requires": ["forge"]},
            {"id": "vg", "from": f"vault_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -3},
            {"id": "mc", "from": f"mark_{suffix}", "to": f"coin_{suffix}", "cost": 1, "heat": 1, "open_rounds": [3, 4, 5]},
        ],
        "contracts": [
            {
                "id": "patient_vault",
                "requires": ["mark", "lock", "forge", "vault"],
                "points": 22 + (index % 2),
                "claimed_order": [f"mark_{suffix}", f"lock_{suffix}", f"forge_{suffix}", f"vault_{suffix}"],
                "final_heat_at_most": 6,
            },
            {
                "id": "coin_bait",
                "requires": ["coin", "mark"],
                "points": 10,
                "exclusive_with": ["patient_vault"],
            },
            {
                "id": "cool_echo",
                "requires": ["cool", "lock"],
                "points": 8,
                "route": [f"lock_{suffix}", f"cool_{suffix}", f"lock_{suffix}"],
            },
            {
                "id": "late_coin_floor",
                "requires": ["coin", "vault"],
                "points": 6,
                "claimed_order": [f"coin_{suffix}", f"vault_{suffix}"],
                "exclusive_with": ["cool_echo"] if index % 2 else [],
            },
        ],
    }


def low_local_high_final_cases() -> list[dict]:
    """Return variants where local site points are a trap for final contract score."""
    return [make_low_local_high_final_case(index) for index in range(10)]


def test_low_local_score_trap_generated_matrix() -> None:
    """Verify the selected route maximizes final score instead of early claimed site points."""
    for idx, match in enumerate(low_local_high_final_cases()):
        input_path = OUT_DIR / f"low_local_high_final_{idx}.json"
        output_path = OUT_DIR / f"low_local_high_final_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_bonus_claim_divergence_case(index: int) -> dict:
    """Build a board where bonus emblems satisfy gates but never appear in claimed order."""
    suffix = f"b{index:02d}"
    bonus_name = ["pass", "writ", "seal"][index % 3]
    consume_bonus = [bonus_name] if index % 2 else []
    return {
        "version": "crescent-1",
        "start": f"dock_{suffix}",
        "round_limit": 8,
        "energy": 7 + (index % 2),
        "energy_cap": 10,
        "heat": index % 2,
        "heat_limit": 8,
        "sites": [
            {"id": f"dock_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"marker_{suffix}", "emblem": "marker", "points": 2, "rest": 3, "echo_points": 3},
            {"id": f"seal_{suffix}", "emblem": "seal", "points": 5, "rest": 1, "seal": [bonus_name]},
            {"id": f"pass_{suffix}", "emblem": "pass", "points": 8, "rest": 0, "seal": ["marker"], "block_rounds": [3]},
            {"id": f"writ_{suffix}", "emblem": "writ", "points": 6, "rest": 1, "seal": ["seal"]},
            {"id": f"court_{suffix}", "emblem": "court", "points": 12, "rest": 0, "seal": ["pass", "writ"]},
            {"id": f"loop_{suffix}", "emblem": "loop", "points": 1, "rest": 4, "echo_points": 4},
        ],
        "links": [
            {"id": "dm", "from": f"dock_{suffix}", "to": f"marker_{suffix}", "cost": 1, "heat": 1, "bonus": {"emblem": bonus_name}},
            {"id": "ms", "from": f"marker_{suffix}", "to": f"seal_{suffix}", "cost": 1, "heat": 1, "requires": [bonus_name]},
            {"id": "sp", "from": f"seal_{suffix}", "to": f"pass_{suffix}", "cost": 2, "heat": 1, "requires": ["seal"], "consumes": consume_bonus},
            {"id": "pw", "from": f"pass_{suffix}", "to": f"writ_{suffix}", "cost": 1, "heat": 1, "requires": ["pass"]},
            {"id": "wc", "from": f"writ_{suffix}", "to": f"court_{suffix}", "cost": 2, "heat": 2, "requires": ["pass", "writ"]},
            {"id": "ml", "from": f"marker_{suffix}", "to": f"loop_{suffix}", "cost": 1, "heat": -1, "bonus": {"energy": 1}},
            {"id": "lm", "from": f"loop_{suffix}", "to": f"marker_{suffix}", "cost": 1, "heat": 1, "safe_revisit": index % 2 == 0, "bonus": {"emblem": bonus_name}},
            {"id": "lp", "from": f"loop_{suffix}", "to": f"pass_{suffix}", "cost": 2, "heat": 1, "requires": [bonus_name], "open_rounds": [4, 5, 6]},
            {"id": "cd", "from": f"court_{suffix}", "to": f"dock_{suffix}", "cost": 1, "heat": -3},
        ],
        "contracts": [
            {
                "id": "bonus_gate",
                "requires": [bonus_name, "seal", "pass"],
                "points": 13 + (index % 2),
                "route": [f"marker_{suffix}", f"loop_{suffix}", f"marker_{suffix}", f"pass_{suffix}"],
            },
            {
                "id": "claimed_only",
                "requires": ["marker", "seal", "pass"],
                "points": 12,
                "claimed_order": [f"marker_{suffix}", f"seal_{suffix}", f"pass_{suffix}"],
                "exclusive_with": ["bonus_gate"] if index % 3 == 0 else [],
            },
            {
                "id": "not_a_claim",
                "requires": [bonus_name],
                "points": 9,
                "claimed_order": [f"{bonus_name}_{suffix}"],
            },
            {
                "id": "court_tail",
                "requires": ["court", "writ"],
                "points": 17,
                "forbids": [bonus_name] if consume_bonus else [],
                "claimed_order": [f"pass_{suffix}", f"writ_{suffix}", f"court_{suffix}"],
            },
        ],
    }


def bonus_claim_divergence_cases() -> list[dict]:
    """Return variants where final emblems and claimed site order intentionally diverge."""
    return [make_bonus_claim_divergence_case(index) for index in range(9)]


def test_bonus_emblems_do_not_create_claimed_sites_matrix() -> None:
    """Verify bonus emblems can satisfy gates and contracts without satisfying claimed-order site ids."""
    for idx, match in enumerate(bonus_claim_divergence_cases()):
        input_path = OUT_DIR / f"bonus_claim_divergence_{idx}.json"
        output_path = OUT_DIR / f"bonus_claim_divergence_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_stop_timing_case(index: int) -> dict:
    """Build a board where taking another legal move can lose final-only contract value."""
    suffix = f"s{index:02d}"
    extra_heat = index % 3
    repeat_safe = index % 2 == 1
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 9,
        "energy": 8,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 9,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"cool_{suffix}", "emblem": "cool", "points": 4, "rest": 3, "echo_points": 4},
            {"id": f"key_{suffix}", "emblem": "key", "points": 5, "rest": 1},
            {"id": f"door_{suffix}", "emblem": "door", "points": 6, "rest": 0, "seal": ["key"]},
            {"id": f"prize_{suffix}", "emblem": "prize", "points": 11, "rest": 0, "seal": ["door"], "late_penalty": {"after": 5, "points": 8}},
            {"id": f"spur_{suffix}", "emblem": "spur", "points": 7, "rest": 0, "seal": ["cool"]},
            {"id": f"ember_{suffix}", "emblem": "ember", "points": 9, "rest": 0, "seal": ["spur"]},
        ],
        "links": [
            {"id": "gc", "from": f"gate_{suffix}", "to": f"cool_{suffix}", "cost": 1, "heat": 1},
            {"id": "ck", "from": f"cool_{suffix}", "to": f"key_{suffix}", "cost": 1, "heat": 1},
            {"id": "kd", "from": f"key_{suffix}", "to": f"door_{suffix}", "cost": 1, "heat": 1, "requires": ["key"]},
            {"id": "dp", "from": f"door_{suffix}", "to": f"prize_{suffix}", "cost": 2, "heat": 2 + extra_heat, "requires": ["door"]},
            {"id": "pc", "from": f"prize_{suffix}", "to": f"cool_{suffix}", "cost": 1, "heat": -2, "safe_revisit": repeat_safe, "bonus": {"energy": 1}},
            {"id": "cs", "from": f"cool_{suffix}", "to": f"spur_{suffix}", "cost": 1, "heat": 2, "requires": ["cool"], "bonus": {"emblem": "door"}},
            {"id": "se", "from": f"spur_{suffix}", "to": f"ember_{suffix}", "cost": 2, "heat": 2, "requires": ["spur"]},
            {"id": "eg", "from": f"ember_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -1},
            {"id": "kg", "from": f"key_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": 0, "safe_revisit": True},
        ],
        "contracts": [
            {
                "id": "cool_prize_window",
                "requires": ["cool", "key", "door", "prize"],
                "points": 20,
                "final_heat_at_most": 5 + (index % 2),
                "final_energy_at_least": 1,
                "claimed_order": [f"cool_{suffix}", f"key_{suffix}", f"door_{suffix}", f"prize_{suffix}"],
            },
            {
                "id": "tempting_spur",
                "requires": ["spur", "ember"],
                "points": 14 + (index % 3),
                "exclusive_with": ["cool_prize_window"],
            },
            {
                "id": "cool_echo_route",
                "requires": ["cool"],
                "points": 7,
                "route": [f"cool_{suffix}", f"key_{suffix}", f"door_{suffix}", f"prize_{suffix}", f"cool_{suffix}"],
            },
            {
                "id": "short_return",
                "requires": ["cool", "key"],
                "points": 8,
                "route": [f"key_{suffix}", f"gate_{suffix}"],
                "exclusive_with": ["cool_echo_route"] if index % 2 else [],
            },
        ],
    }


def stop_timing_cases() -> list[dict]:
    """Return variants that require considering all legal stop points."""
    return [make_stop_timing_case(index) for index in range(9)]


def test_stop_timing_generated_matrix() -> None:
    """Verify the best plan may stop before taking another legal move that lowers final contract value."""
    for idx, match in enumerate(stop_timing_cases()):
        input_path = OUT_DIR / f"stop_timing_{idx}.json"
        output_path = OUT_DIR / f"stop_timing_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_penalty_chain_floor_case(index: int) -> dict:
    """Build a board where late penalty floors before chain points are added."""
    suffix = f"p{index:02d}"
    block_round = 2 + (index % 3)
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 8,
        "energy": 7 + (index % 2),
        "energy_cap": 10,
        "heat": index % 2,
        "heat_limit": 8,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"seed_{suffix}", "emblem": "seed", "points": 3, "rest": 3, "echo_points": 3},
            {"id": f"late_{suffix}", "emblem": "late", "points": 4, "rest": 1, "late_penalty": {"after": 2, "points": 9}, "chain_points": {"after": f"seed_{suffix}", "points": 8}},
            {"id": f"blocked_{suffix}", "emblem": "blocked", "points": 6, "rest": 1, "block_rounds": [block_round], "chain_points": {"after": f"late_{suffix}", "points": 5}},
            {"id": f"seal_{suffix}", "emblem": "seal", "points": 8, "rest": 0, "seal": ["late"]},
            {"id": f"crown_{suffix}", "emblem": "crown", "points": 10, "rest": 0, "seal": ["blocked", "seal"]},
            {"id": f"relay_{suffix}", "emblem": "relay", "points": 2, "rest": 4, "echo_points": 4},
        ],
        "links": [
            {"id": "gs", "from": f"gate_{suffix}", "to": f"seed_{suffix}", "cost": 1, "heat": 1},
            {"id": "sl", "from": f"seed_{suffix}", "to": f"late_{suffix}", "cost": 2, "heat": 1},
            {"id": "lr", "from": f"late_{suffix}", "to": f"relay_{suffix}", "cost": 1, "heat": -1, "bonus": {"energy": 1}},
            {"id": "rb", "from": f"relay_{suffix}", "to": f"blocked_{suffix}", "cost": 1, "heat": 1, "requires": ["late"], "open_rounds": [3, 4, 5, 6]},
            {"id": "br", "from": f"blocked_{suffix}", "to": f"relay_{suffix}", "cost": 1, "heat": 1, "safe_revisit": index % 2 == 0, "bonus": {"emblem": "late"}},
            {"id": "rs", "from": f"relay_{suffix}", "to": f"seal_{suffix}", "cost": 2, "heat": 1, "requires": ["late"]},
            {"id": "sc", "from": f"seal_{suffix}", "to": f"crown_{suffix}", "cost": 2, "heat": 2, "requires": ["seal", "blocked"]},
            {"id": "cg", "from": f"crown_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -3},
            {"id": "sr", "from": f"seed_{suffix}", "to": f"relay_{suffix}", "cost": 1, "heat": 0, "bonus": {"emblem": "late"}},
        ],
        "contracts": [
            {
                "id": "floor_then_chain",
                "requires": ["seed", "late", "blocked"],
                "points": 15,
                "claimed_order": [f"seed_{suffix}", f"late_{suffix}", f"blocked_{suffix}"],
            },
            {
                "id": "relay_echo",
                "requires": ["relay", "late"],
                "points": 9 + (index % 2),
                "route": [f"late_{suffix}", f"relay_{suffix}", f"blocked_{suffix}", f"relay_{suffix}"],
                "exclusive_with": ["crown_full"] if index % 3 == 0 else [],
            },
            {
                "id": "crown_full",
                "requires": ["seed", "late", "blocked", "seal", "crown"],
                "points": 21,
                "final_heat_at_most": 7,
                "claimed_order": [f"blocked_{suffix}", f"seal_{suffix}", f"crown_{suffix}"],
            },
            {
                "id": "bonus_late_not_claim",
                "requires": ["late", "late"],
                "points": 7,
                "claimed_order": [f"late_{suffix}", f"late_{suffix}"],
            },
        ],
    }


def penalty_chain_floor_cases() -> list[dict]:
    """Return variants that distinguish late-penalty flooring from chain scoring."""
    return [make_penalty_chain_floor_case(index) for index in range(9)]


def test_late_penalty_floor_before_chain_generated_matrix() -> None:
    """Verify late penalties floor site points before chain points are added."""
    for idx, match in enumerate(penalty_chain_floor_cases()):
        input_path = OUT_DIR / f"penalty_chain_floor_{idx}.json"
        output_path = OUT_DIR / f"penalty_chain_floor_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_resource_tie_after_contract_case(index: int) -> dict:
    """Build a board where final resource tie-breaks matter after equal scoring and contracts."""
    suffix = f"r{index:02d}"
    quiet = 3 + (index % 3)
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 6,
        "energy": 6 + (index % 2),
        "energy_cap": 8,
        "heat": 0,
        "heat_limit": 7,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"alpha_{suffix}", "emblem": "alpha", "points": 5, "rest": 1},
            {"id": f"bravo_{suffix}", "emblem": "bravo", "points": 5, "rest": 0},
            {"id": f"charlie_{suffix}", "emblem": "charlie", "points": 4, "rest": 3},
            {"id": f"delta_{suffix}", "emblem": "delta", "points": 5, "rest": 0, "seal": ["alpha"]},
            {"id": f"echo_{suffix}", "emblem": "echo", "points": 5, "rest": 0, "seal": ["charlie"]},
        ],
        "links": [
            {"id": "ga", "from": f"gate_{suffix}", "to": f"alpha_{suffix}", "cost": 1, "heat": 1},
            {"id": "gb", "from": f"gate_{suffix}", "to": f"bravo_{suffix}", "cost": 1, "heat": 0},
            {"id": "ac", "from": f"alpha_{suffix}", "to": f"charlie_{suffix}", "cost": 1, "heat": 1, "bonus": {"energy": 1}},
            {"id": "bc", "from": f"bravo_{suffix}", "to": f"charlie_{suffix}", "cost": 1, "heat": 2, "bonus": {"emblem": "alpha"}},
            {"id": "cd", "from": f"charlie_{suffix}", "to": f"delta_{suffix}", "cost": 2, "heat": 1, "requires": ["alpha"], "quiet_max_heat": quiet},
            {"id": "ce", "from": f"charlie_{suffix}", "to": f"echo_{suffix}", "cost": 1 + (index % 2), "heat": 0, "requires": ["charlie"]},
            {"id": "dg", "from": f"delta_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -1},
            {"id": "eg", "from": f"echo_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": 0},
        ],
        "contracts": [
            {
                "id": "left_pair",
                "requires": ["alpha", "charlie", "delta"],
                "points": 11,
                "route": [f"alpha_{suffix}", f"charlie_{suffix}", f"delta_{suffix}"],
                "exclusive_with": ["right_pair"],
            },
            {
                "id": "right_pair",
                "requires": ["bravo", "charlie", "echo"],
                "points": 11,
                "route": [f"bravo_{suffix}", f"charlie_{suffix}", f"echo_{suffix}"],
                "exclusive_with": ["left_pair"],
            },
            {
                "id": "shared_core",
                "requires": ["charlie"],
                "points": 6,
                "final_energy_at_least": 1,
            },
            {
                "id": "heat_window",
                "requires": ["alpha"],
                "points": 4,
                "final_heat_at_most": 3 + (index % 2),
            },
        ],
    }


def resource_tie_after_contract_cases() -> list[dict]:
    """Return variants where final tie-breaks are only visible after contract scoring."""
    return [make_resource_tie_after_contract_case(index) for index in range(9)]


def test_resource_tie_after_contract_generated_matrix() -> None:
    """Verify score ties compare heat, energy, path length, path string, and contracts in order."""
    for idx, match in enumerate(resource_tie_after_contract_cases()):
        input_path = OUT_DIR / f"resource_tie_after_contract_{idx}.json"
        output_path = OUT_DIR / f"resource_tie_after_contract_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_consume_reacquire_forbid_case(index: int) -> dict:
    """Build a board where consumed emblems can be reacquired before final contract checks."""
    suffix = f"u{index:02d}"
    spend_twice = index % 3 == 0
    restore_on_return = index % 2 == 0
    heat_limit = 7 + (index % 2)
    spend = ["sigil", "sigil"] if spend_twice else ["sigil"]
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 9,
        "energy": 8,
        "energy_cap": 10,
        "heat": index % 2,
        "heat_limit": heat_limit,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"sigil_{suffix}", "emblem": "sigil", "points": 4, "rest": 2, "echo_points": 3},
            {"id": f"mint_{suffix}", "emblem": "mint", "points": 3, "rest": 4, "block_rounds": [3]},
            {"id": f"spent_{suffix}", "emblem": "spent", "points": 7, "rest": 1, "seal": ["mint"]},
            {"id": f"restore_{suffix}", "emblem": "restore", "points": 5, "rest": 2, "seal": ["spent"]},
            {"id": f"final_{suffix}", "emblem": "final", "points": 12, "rest": 0, "seal": ["restore", "sigil"]},
            {"id": f"cold_{suffix}", "emblem": "cold", "points": 2, "rest": 3, "echo_points": 4},
        ],
        "links": [
            {"id": "gs", "from": f"gate_{suffix}", "to": f"sigil_{suffix}", "cost": 1, "heat": 1},
            {"id": "sm", "from": f"sigil_{suffix}", "to": f"mint_{suffix}", "cost": 1, "heat": 1, "bonus": {"emblem": "sigil"}},
            {"id": "ms", "from": f"mint_{suffix}", "to": f"sigil_{suffix}", "cost": 1, "heat": 1, "safe_revisit": True, "bonus": {"emblem": "sigil"} if restore_on_return else {"energy": 1}},
            {"id": "mp", "from": f"mint_{suffix}", "to": f"spent_{suffix}", "cost": 2, "heat": 1, "requires": ["sigil"], "consumes": spend},
            {"id": "pc", "from": f"spent_{suffix}", "to": f"cold_{suffix}", "cost": 1, "heat": -1, "bonus": {"energy": 1}},
            {"id": "cr", "from": f"cold_{suffix}", "to": f"restore_{suffix}", "cost": 1, "heat": 1, "requires": ["spent"], "bonus": {"emblem": "sigil"}},
            {"id": "rf", "from": f"restore_{suffix}", "to": f"final_{suffix}", "cost": 2, "heat": 2, "requires": ["restore", "sigil"]},
            {"id": "fg", "from": f"final_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -3},
            {"id": "sc", "from": f"sigil_{suffix}", "to": f"cold_{suffix}", "cost": 2, "heat": 0, "bonus": {"emblem": "mint"}},
            {"id": "cm", "from": f"cold_{suffix}", "to": f"mint_{suffix}", "cost": 1, "heat": 1, "open_rounds": [3, 4, 5, 6]},
        ],
        "contracts": [
            {
                "id": "spent_clean",
                "requires": ["mint", "spent", "restore"],
                "forbids": ["sigil"] if spend_twice and not restore_on_return else [],
                "points": 15,
                "claimed_order": [f"mint_{suffix}", f"spent_{suffix}", f"restore_{suffix}"],
                "exclusive_with": ["final_restock"] if index % 2 else [],
            },
            {
                "id": "final_restock",
                "requires": ["sigil", "restore", "final"],
                "points": 20 + (index % 2),
                "route": [f"mint_{suffix}", f"spent_{suffix}", f"cold_{suffix}", f"restore_{suffix}", f"final_{suffix}"],
                "final_heat_at_most": heat_limit - 1,
            },
            {
                "id": "double_sigil_final",
                "requires": ["sigil", "sigil", "final"],
                "points": 10,
                "exclusive_with": ["spent_clean"],
            },
            {
                "id": "cold_echo_tail",
                "requires": ["cold", "sigil"],
                "points": 8,
                "route": [f"sigil_{suffix}", f"mint_{suffix}", f"sigil_{suffix}", f"mint_{suffix}"],
            },
        ],
    }


def consume_reacquire_forbid_cases() -> list[dict]:
    """Return variants that require exact final multiset accounting after consumes and bonuses."""
    return [make_consume_reacquire_forbid_case(index) for index in range(9)]


def test_consume_reacquire_forbid_generated_matrix() -> None:
    """Verify consumed emblems, reacquired bonuses, final forbids, and repeated requirements interact."""
    for idx, match in enumerate(consume_reacquire_forbid_cases()):
        input_path = OUT_DIR / f"consume_reacquire_forbid_{idx}.json"
        output_path = OUT_DIR / f"consume_reacquire_forbid_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_independent_multiset_gate_case(index: int) -> dict:
    """Build a board where requires and consumes must be checked as separate multiset gates."""
    suffix = f"x{index:02d}"
    double_spend = index % 3 == 1
    mirror_block = [2] if index % 4 in (0, 3) else []
    vault_requires = ["glyph", "glyph"] if index % 2 == 0 else ["glyph", "glyph", "mirror"]
    vault_consumes = ["glyph", "glyph"] if double_spend else ["glyph"]
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 8,
        "energy": 8,
        "energy_cap": 11,
        "heat": index % 2,
        "heat_limit": 8,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"glyph_{suffix}", "emblem": "glyph", "points": 4, "rest": 3, "echo_points": 2},
            {"id": f"mirror_{suffix}", "emblem": "mirror", "points": 7, "rest": 1, "seal": ["glyph"], "block_rounds": mirror_block},
            {"id": f"well_{suffix}", "emblem": "well", "points": 2, "rest": 3, "echo_points": 3},
            {"id": f"vault_{suffix}", "emblem": "vault", "points": 14, "rest": 0, "seal": ["mirror"]},
            {"id": f"crown_{suffix}", "emblem": "crown", "points": 10, "rest": 0, "seal": ["vault", "glyph"]},
        ],
        "links": [
            {"id": "gg", "from": f"gate_{suffix}", "to": f"glyph_{suffix}", "cost": 1, "heat": 1},
            {
                "id": "gm",
                "from": f"glyph_{suffix}",
                "to": f"mirror_{suffix}",
                "cost": 1,
                "heat": 1,
                "requires": ["glyph"],
                "consumes": ["glyph"],
                "bonus": {"emblem": "glyph"},
            },
            {"id": "mw", "from": f"mirror_{suffix}", "to": f"well_{suffix}", "cost": 1, "heat": -1, "bonus": {"emblem": "glyph", "energy": 1}},
            {"id": "wg", "from": f"well_{suffix}", "to": f"glyph_{suffix}", "cost": 1, "heat": 1, "safe_revisit": True, "bonus": {"emblem": "glyph"}},
            {
                "id": "mv",
                "from": f"mirror_{suffix}",
                "to": f"vault_{suffix}",
                "cost": 2,
                "heat": 2,
                "requires": vault_requires,
                "consumes": vault_consumes,
                "bonus": {"emblem": "glyph"} if index % 5 == 0 else {"energy": 1},
            },
            {"id": "vc", "from": f"vault_{suffix}", "to": f"crown_{suffix}", "cost": 2, "heat": 2, "requires": ["vault", "glyph"]},
            {"id": "vg", "from": f"vault_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -3},
            {"id": "wv", "from": f"well_{suffix}", "to": f"vault_{suffix}", "cost": 3, "heat": 1, "requires": ["glyph", "glyph"], "open_rounds": [5, 6, 7]},
        ],
        "contracts": [
            {
                "id": "clean_vault",
                "requires": ["mirror", "vault"],
                "forbids": ["glyph"] if double_spend else [],
                "points": 17,
                "claimed_order": [f"mirror_{suffix}", f"vault_{suffix}"],
            },
            {
                "id": "restocked_crown",
                "requires": ["glyph", "vault", "crown"],
                "points": 21,
                "route": [f"glyph_{suffix}", f"mirror_{suffix}", f"well_{suffix}", f"glyph_{suffix}", f"mirror_{suffix}", f"vault_{suffix}"],
                "exclusive_with": ["clean_vault"] if index % 2 else [],
            },
            {
                "id": "mirror_echo",
                "requires": ["glyph", "mirror", "well"],
                "points": 9,
                "route": [f"mirror_{suffix}", f"well_{suffix}", f"glyph_{suffix}", f"mirror_{suffix}"],
            },
            {
                "id": "double_glyph_finish",
                "requires": ["glyph", "glyph", "vault"],
                "points": 11,
                "final_heat_at_most": 7,
                "exclusive_with": ["mirror_echo"],
            },
        ],
    }


def independent_multiset_gate_cases() -> list[dict]:
    """Return variants that punish combining requires and consumes into one count check."""
    return [make_independent_multiset_gate_case(index) for index in range(14)]


def test_independent_requires_and_consumes_multiset_matrix() -> None:
    """Verify requires and consumes are each satisfied from the pre-link multiset, not summed together."""
    for idx, match in enumerate(independent_multiset_gate_cases()):
        input_path = OUT_DIR / f"independent_multiset_{idx}.json"
        output_path = OUT_DIR / f"independent_multiset_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_delayed_bonus_claim_case(index: int) -> dict:
    """Build a board where a same-link bonus cannot open arrival but can enable a later claim."""
    suffix = f"b{index:02d}"
    consume_on_gate = ["key"] if index % 2 else []
    return {
        "version": "crescent-1",
        "start": f"start_{suffix}",
        "round_limit": 9,
        "energy": 7,
        "energy_cap": 10,
        "heat": 0,
        "heat_limit": 8,
        "sites": [
            {"id": f"start_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"key_{suffix}", "emblem": "key", "points": 4, "rest": 2},
            {"id": f"sealed_{suffix}", "emblem": "sealed", "points": 12, "rest": 0, "seal": ["key"]},
            {"id": f"loop_{suffix}", "emblem": "loop", "points": 3, "rest": 3, "echo_points": 4},
            {"id": f"court_{suffix}", "emblem": "court", "points": 9, "rest": 0, "seal": ["sealed", "key"]},
            {"id": f"cool_{suffix}", "emblem": "cool", "points": 2, "rest": 2},
        ],
        "links": [
            {"id": "sk", "from": f"start_{suffix}", "to": f"key_{suffix}", "cost": 1, "heat": 1},
            {
                "id": "ks",
                "from": f"key_{suffix}",
                "to": f"sealed_{suffix}",
                "cost": 1,
                "heat": 1,
                "requires": ["key"],
                "consumes": ["key"],
                "bonus": {"emblem": "key"},
            },
            {"id": "sl", "from": f"sealed_{suffix}", "to": f"loop_{suffix}", "cost": 1, "heat": -1, "bonus": {"emblem": "key", "energy": 1}},
            {"id": "lk", "from": f"loop_{suffix}", "to": f"key_{suffix}", "cost": 1, "heat": 1, "safe_revisit": True, "bonus": {"emblem": "key"}},
            {
                "id": "ks",
                "from": f"key_{suffix}",
                "to": f"sealed_{suffix}",
                "cost": 1,
                "heat": 1,
                "requires": ["key", "key"],
                "consumes": consume_on_gate,
                "bonus": {"energy": 1},
            },
            {"id": "sc", "from": f"sealed_{suffix}", "to": f"court_{suffix}", "cost": 2, "heat": 2, "requires": ["sealed", "key"]},
            {"id": "lc", "from": f"loop_{suffix}", "to": f"cool_{suffix}", "cost": 1, "heat": -2, "open_rounds": [4, 5, 6]},
            {"id": "cs", "from": f"cool_{suffix}", "to": f"sealed_{suffix}", "cost": 2, "heat": 1, "requires": ["key"], "bonus": {"emblem": "key"}},
        ],
        "contracts": [
            {
                "id": "late_seal",
                "requires": ["sealed", "court"],
                "points": 20,
                "claimed_order": [f"sealed_{suffix}", f"court_{suffix}"],
                "exclusive_with": ["path_only"],
            },
            {
                "id": "path_only",
                "requires": ["key", "loop"],
                "points": 13,
                "route": [f"sealed_{suffix}", f"loop_{suffix}", f"key_{suffix}", f"sealed_{suffix}"],
            },
            {
                "id": "cool_tail",
                "requires": ["cool", "key"],
                "points": 8 + (index % 3),
                "final_heat_at_most": 4,
            },
            {
                "id": "keyless_finish",
                "requires": ["sealed"],
                "forbids": ["key"] if consume_on_gate else [],
                "points": 7,
            },
        ],
    }


def delayed_bonus_claim_cases() -> list[dict]:
    """Return variants where path history and bonus timing decide whether a site is ever claimed."""
    return [make_delayed_bonus_claim_case(index) for index in range(10)]


def test_delayed_bonus_cannot_open_same_arrival_matrix() -> None:
    """Verify link bonus timing, blocked first claims, repeated link cost, and later claims interact."""
    for idx, match in enumerate(delayed_bonus_claim_cases()):
        input_path = OUT_DIR / f"delayed_bonus_claim_{idx}.json"
        output_path = OUT_DIR / f"delayed_bonus_claim_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)


def make_negative_heat_order_case(index: int) -> dict:
    """Build a board where negative heat is not clamped and decides final ordering."""
    suffix = f"n{index:02d}"
    safe_loop = index % 2 == 0
    quiet_gate = 1 + (index % 3)
    return {
        "version": "crescent-1",
        "start": f"gate_{suffix}",
        "round_limit": 7,
        "energy": 7,
        "energy_cap": 9,
        "heat": index % 2,
        "heat_limit": 7,
        "sites": [
            {"id": f"gate_{suffix}", "emblem": "none", "points": 0, "rest": 0},
            {"id": f"warm_{suffix}", "emblem": "warm", "points": 5, "rest": 1},
            {"id": f"cool_{suffix}", "emblem": "cool", "points": 5, "rest": 1, "echo_points": 3},
            {"id": f"key_{suffix}", "emblem": "key", "points": 4, "rest": 2, "seal": ["cool"]},
            {"id": f"vault_{suffix}", "emblem": "vault", "points": 8, "rest": 0, "seal": ["key"]},
            {"id": f"tail_{suffix}", "emblem": "tail", "points": 5, "rest": 0, "seal": ["warm"]},
        ],
        "links": [
            {"id": "gw", "from": f"gate_{suffix}", "to": f"warm_{suffix}", "cost": 1, "heat": 1},
            {"id": "gc", "from": f"gate_{suffix}", "to": f"cool_{suffix}", "cost": 1, "heat": -2, "bonus": {"energy": 1}},
            {"id": "cw", "from": f"cool_{suffix}", "to": f"warm_{suffix}", "cost": 1, "heat": -1, "safe_revisit": safe_loop, "bonus": {"emblem": "warm"}},
            {"id": "wc", "from": f"warm_{suffix}", "to": f"cool_{suffix}", "cost": 1, "heat": -2, "safe_revisit": True, "bonus": {"emblem": "cool"}},
            {"id": "ck", "from": f"cool_{suffix}", "to": f"key_{suffix}", "cost": 2, "heat": 2, "requires": ["cool"], "quiet_max_heat": quiet_gate},
            {"id": "kv", "from": f"key_{suffix}", "to": f"vault_{suffix}", "cost": 2, "heat": 2, "requires": ["key"]},
            {"id": "wt", "from": f"warm_{suffix}", "to": f"tail_{suffix}", "cost": 2, "heat": 0, "requires": ["warm"]},
            {"id": "tg", "from": f"tail_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -3},
            {"id": "vg", "from": f"vault_{suffix}", "to": f"gate_{suffix}", "cost": 1, "heat": -4},
        ],
        "contracts": [
            {
                "id": "cold_vault",
                "requires": ["cool", "key", "vault"],
                "points": 16,
                "final_heat_at_most": 1,
                "route": [f"cool_{suffix}", f"warm_{suffix}", f"cool_{suffix}", f"key_{suffix}", f"vault_{suffix}"],
            },
            {
                "id": "warm_tail",
                "requires": ["warm", "tail"],
                "points": 13 + (index % 2),
                "claimed_order": [f"warm_{suffix}", f"tail_{suffix}"],
                "exclusive_with": ["cold_vault"] if index % 3 == 0 else [],
            },
            {
                "id": "cool_echo",
                "requires": ["cool", "warm"],
                "points": 8,
                "route": [f"cool_{suffix}", f"warm_{suffix}", f"cool_{suffix}"],
            },
            {
                "id": "negative_finish",
                "requires": ["vault"],
                "points": 4,
                "final_heat_at_most": -1,
            },
        ],
    }


def negative_heat_order_cases() -> list[dict]:
    """Return variants where unclamped negative heat affects gates, contracts, and tie-breaks."""
    return [make_negative_heat_order_case(index) for index in range(8)]


def test_negative_heat_order_generated_matrix() -> None:
    """Verify negative heat is preserved and participates in final contract gates and tie-breaks."""
    for idx, match in enumerate(negative_heat_order_cases()):
        input_path = OUT_DIR / f"negative_heat_order_{idx}.json"
        output_path = OUT_DIR / f"negative_heat_order_{idx}_result.json"
        input_path.write_text(json.dumps(match, separators=(",", ":")), encoding="utf-8")
        result = run_scorer(input_path, output_path)
        assert_schema(result)
        assert result == expected_result(match)
