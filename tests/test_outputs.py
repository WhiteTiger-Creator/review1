import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path("/app") if Path("/app/environment").exists() else Path(__file__).resolve().parents[1]
ENV = ROOT / "environment"
SRC = ENV / "src" / "flux_recon.cpp"
BUNDLED = ENV / "cases"


DIRS = {
    "N": (-1, 0),
    "S": (1, 0),
    "E": (0, 1),
    "WST": (0, -1),
    "DN": (-1, 0),
    "DS": (1, 0),
    "DE": (0, 1),
    "DW": (0, -1),
}


class InvalidCase(ValueError):
    pass


@pytest.fixture(scope="session")
def binary(tmp_path_factory):
    build_dir = tmp_path_factory.mktemp("build")
    exe = build_dir / "flux_recon"
    subprocess.run(
        ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", str(SRC), "-o", str(exe)],
        check=True,
    )
    return exe


def strip_comments(text):
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        tokens.extend(line.split())
    return tokens


def parse_case(path):
    toks = strip_comments(path.read_text())
    idx = 0

    def need(expected=None):
        nonlocal idx
        if idx >= len(toks):
            raise InvalidCase("unexpected end")
        tok = toks[idx]
        idx += 1
        if expected is not None and tok != expected:
            raise InvalidCase(f"expected {expected}, got {tok}")
        return tok

    need("case_id")
    case_id = need()
    if not case_id.replace("-", "").replace("_", "").isalnum():
        raise InvalidCase("bad case id")
    need("rows")
    rows = int(need())
    need("cols")
    cols = int(need())
    need("rounds")
    rounds = int(need())
    if rows <= 0 or cols <= 0 or rounds <= 0:
        raise InvalidCase("bad dimensions")
    need("grid")
    grid = []
    for _ in range(rows):
        row = need()
        if len(row) != cols:
            raise InvalidCase("wrong row length")
        for ch in row:
            if ch not in "#.EH0123456789+PGT":
                raise InvalidCase("bad grid char")
        grid.append(row)
    need("end_grid")
    portals = {}
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch.isdigit():
                portals.setdefault(ch, []).append((r, c))
    for cells in portals.values():
        if len(cells) != 2:
            raise InvalidCase("portal count")

    need("actors")
    actors = {}
    starts = set()
    while True:
        tok = need()
        if tok == "end_actors":
            break
        actor_id = tok
        if not actor_id.replace("-", "").replace("_", "").isalnum() or actor_id in actors:
            raise InvalidCase("bad actor")
        r = int(need())
        c = int(need())
        energy = int(need())
        priority = int(need())
        if not (0 <= r < rows and 0 <= c < cols) or grid[r][c] == "#":
            raise InvalidCase("bad actor position")
        if (r, c) in starts:
            raise InvalidCase("duplicate position")
        if energy < 0 or energy > 9 or priority < 0 or priority > 99:
            raise InvalidCase("bad actor stats")
        starts.add((r, c))
        actors[actor_id] = {
            "id": actor_id,
            "row": r,
            "col": c,
            "energy": energy,
            "priority": priority,
            "status": "active",
            "bumps": 0,
            "blocks": 0,
        }
    if not actors:
        raise InvalidCase("no actors")

    need("commands")
    commands = {}
    while True:
        tok = need()
        if tok == "end_commands":
            break
        actor_id = tok
        if actor_id not in actors or actor_id in commands:
            raise InvalidCase("bad command actor")
        row = [need() for _ in range(rounds)]
        if any(cmd not in {"W", "N", "S", "E", "WST", "DN", "DS", "DE", "DW"} for cmd in row):
            raise InvalidCase("bad command")
        commands[actor_id] = row
    if set(commands) != set(actors):
        raise InvalidCase("missing commands")
    if idx != len(toks):
        raise InvalidCase("trailing tokens")
    return {
        "case_id": case_id,
        "rows": rows,
        "cols": cols,
        "rounds": rounds,
        "grid": grid,
        "portals": portals,
        "actors": actors,
        "commands": commands,
    }


def fnv(tokens):
    h = 0xCBF29CE484222325
    for token in tokens:
        for b in token.encode("ascii"):
            h ^= b
            h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def portal_target(case, r, c):
    ch = case["grid"][r][c]
    if not ch.isdigit():
        return r, c, None
    cells = case["portals"][ch]

    target = cells[1] if cells[0] == (r, c) else cells[0]
    return target[0], target[1], ch


def turret_hits(case, row, col, gates_open):
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        r, c = row + dr, col + dc
        while 0 <= r < case["rows"] and 0 <= c < case["cols"]:
            tile = case["grid"][r][c]
            if tile == "#" or (tile == "G" and not gates_open):
                break
            if tile == "T":
                return True
            r += dr
            c += dc
    return False


def simulate_case(case, max_rounds=None):
    actors = {aid: dict(actor) for aid, actor in case["actors"].items()}
    rounds = min(case["rounds"], max_rounds) if max_rounds is not None else case["rounds"]
    echoes = set()
    events = []
    gates_open = False

    for rnd in range(rounds):
        active_ids = [aid for aid in sorted(actors) if actors[aid]["status"] == "active"]
        proposals = {}
        costs = {}
        blocked_initial = set()
        for aid in active_ids:
            actor = actors[aid]
            cmd = case["commands"][aid][rnd]
            cost = 0 if cmd == "W" else (2 if cmd.startswith("D") else 1)
            if actor["energy"] < cost:
                events.append(f"r{rnd}:{aid}:tired")
                proposals[aid] = (actor["row"], actor["col"])
                costs[aid] = 0
                continue
            if cmd == "W":
                proposals[aid] = (actor["row"], actor["col"])
                costs[aid] = 0
                continue
            dr, dc = DIRS[cmd]
            steps = 2 if cmd.startswith("D") else 1
            cr, cc = actor["row"], actor["col"]
            failed = False
            for _ in range(steps):
                nr, nc = cr + dr, cc + dc
                if not (0 <= nr < case["rows"] and 0 <= nc < case["cols"]) or case["grid"][nr][nc] == "#":
                    events.append(f"r{rnd}:{aid}:wall")
                    failed = True
                    break
                if case["grid"][nr][nc] == "G" and not gates_open:
                    events.append(f"r{rnd}:{aid}:gate")
                    failed = True
                    break
                if (nr, nc) in echoes:
                    events.append(f"r{rnd}:{aid}:echo")
                    failed = True
                    break
                cr, cc = nr, nc
                pr, pc, digit = portal_target(case, cr, cc)
                if digit is not None:
                    cr, cc = pr, pc
                    events.append(f"r{rnd}:{aid}:portal:{digit}")
            if failed:
                proposals[aid] = (actor["row"], actor["col"])
                costs[aid] = 0
                blocked_initial.add(aid)
            else:
                proposals[aid] = (cr, cc)
                costs[aid] = cost

        accepted = {aid for aid in active_ids if proposals[aid] != (actors[aid]["row"], actors[aid]["col"])}
        dest_to_ids = {}
        for aid in accepted:
            dest_to_ids.setdefault(proposals[aid], []).append(aid)
        for dest in sorted(dest_to_ids):
            ids = sorted(dest_to_ids[dest])
            if len(ids) > 1:
                winner = min(ids, key=lambda x: (actors[x]["priority"], x))
                for aid in ids:
                    if aid != winner:
                        accepted.discard(aid)
                        actors[aid]["bumps"] += 1
                        events.append(f"r{rnd}:{aid}:bump:{winner}")

        changed = True
        while changed:
            changed = False
            occupied_by = {(actors[aid]["row"], actors[aid]["col"]): aid for aid in active_ids}
            for aid in sorted(accepted):
                dest = proposals[aid]
                occupant = occupied_by.get(dest)
                if occupant is None or occupant == aid:
                    continue
                direct_swap = occupant in accepted and proposals[occupant] == (actors[aid]["row"], actors[aid]["col"])
                if direct_swap:
                    continue
                if occupant not in accepted:
                    accepted.discard(aid)
                    actors[aid]["blocks"] += 1
                    events.append(f"r{rnd}:{aid}:blocked:{occupant}")
                    changed = True
                    break

        next_echoes = set()
        for aid in sorted(active_ids):
            actor = actors[aid]
            start = (actor["row"], actor["col"])
            if aid in accepted:
                actor["row"], actor["col"] = proposals[aid]
                actor["energy"] -= costs[aid]
                if start != proposals[aid]:
                    next_echoes.add(start)
            elif costs[aid] == 0 and proposals[aid] == start and aid not in blocked_initial:
                actor["energy"] = min(9, actor["energy"] + 1)

        for aid in sorted(active_ids):
            actor = actors[aid]
            if actor["status"] != "active":
                continue
            tile = case["grid"][actor["row"]][actor["col"]]
            if tile == "H":
                actor["energy"] -= 1
                events.append(f"r{rnd}:{aid}:hazard")
            if tile == "+":
                before = actor["energy"]
                actor["energy"] = min(9, actor["energy"] + 2)
                if actor["energy"] != before:
                    events.append(f"r{rnd}:{aid}:charge")
            if actor["energy"] < 0:
                actor["status"] = "down"
                events.append(f"r{rnd}:{aid}:down")

        if not gates_open and any(
            actors[aid]["status"] == "active" and case["grid"][actors[aid]["row"]][actors[aid]["col"]] == "P"
            for aid in active_ids
        ):
            gates_open = True
            events.append(f"r{rnd}:arena:gate_open")

        for aid in sorted(active_ids):
            actor = actors[aid]
            if actor["status"] != "active":
                continue
            if turret_hits(case, actor["row"], actor["col"], gates_open):
                actor["energy"] -= 2
                events.append(f"r{rnd}:{aid}:laser")
                if actor["energy"] < 0:
                    actor["status"] = "down"
                    events.append(f"r{rnd}:{aid}:down")

        for aid in sorted(active_ids):
            actor = actors[aid]
            if actor["status"] == "active" and case["grid"][actor["row"]][actor["col"]] == "E":
                actor["status"] = "exited"
                events.append(f"r{rnd}:{aid}:exit")

        echoes = next_echoes

    actor_rows = []
    for aid in sorted(actors):
        actor = actors[aid]
        actor_rows.append(
            {
                "id": aid,
                "row": actor["row"],
                "col": actor["col"],
                "energy": actor["energy"],
                "status": actor["status"],
                "bumps": actor["bumps"],
                "blocks": actor["blocks"],
            }
        )
    score = 0
    for actor in actor_rows:
        if actor["status"] == "exited":
            score += 100
        if actor["status"] == "down":
            score -= 40
        else:
            score += 5 * actor["energy"]
        score -= 7 * actor["bumps"]
        score -= 3 * actor["blocks"]
    digest_tokens = [f"case:{case['case_id']}", f"rounds:{rounds}"]
    digest_tokens.extend(
        f"actor:{a['id']}:{a['row']}:{a['col']}:{a['energy']}:{a['status']}:{a['bumps']}:{a['blocks']}"
        for a in actor_rows
    )
    digest_tokens.extend(f"event:{event}" for event in events)
    digest_tokens.append(f"score:{score}")
    return {
        "case_id": case["case_id"],
        "rounds_completed": rounds,
        "actors": actor_rows,
        "events": events,
        "score": score,
        "digest": fnv(digest_tokens),
    }


def expected_report(case_dir, max_rounds=None):
    cases = [parse_case(path) for path in Path(case_dir).glob("*.flux")]
    matches = sorted((simulate_case(case, max_rounds=max_rounds) for case in cases), key=lambda item: item["case_id"])
    total_score = sum(match["score"] for match in matches)
    exited_count = sum(actor["status"] == "exited" for match in matches for actor in match["actors"])
    down_count = sum(actor["status"] == "down" for match in matches for actor in match["actors"])
    tokens = [f"match:{m['case_id']}:{m['digest']}:{m['score']}" for m in matches]
    tokens.append(f"counts:{len(matches)}:{total_score}:{exited_count}:{down_count}")
    return {
        "matches": matches,
        "summary": {
            "match_count": len(matches),
            "total_score": total_score,
            "exited_count": exited_count,
            "down_count": down_count,
            "digest": fnv(tokens),
        },
    }


def run_tool(binary, case_dir, out_path, extra=None, check=True):
    cmd = [str(binary), "--case-dir", str(case_dir), "--out", str(out_path)]
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def assert_report(actual, expected):
    assert actual == expected
    assert list(actual) == ["matches", "summary"]
    assert list(actual["summary"]) == ["match_count", "total_score", "exited_count", "down_count", "digest"]
    for match in actual["matches"]:
        assert list(match) == ["case_id", "rounds_completed", "actors", "events", "score", "digest"]
        for actor in match["actors"]:
            assert list(actor) == ["id", "row", "col", "energy", "status", "bumps", "blocks"]
            assert actor["status"] in {"active", "exited", "down"}
            assert isinstance(actor["row"], int)
            assert isinstance(actor["energy"], int)
        assert len(match["digest"]) == 16
    assert len(actual["summary"]["digest"]) == 16


def copy_bundled(tmp_path):
    case_dir = tmp_path / "cases"
    shutil.copytree(BUNDLED, case_dir)
    return case_dir


def write_case(directory, name, text):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text.strip() + "\n")
    return path


def test_bundled_replays_match_reference_and_digest(binary, tmp_path):
    case_dir = copy_bundled(tmp_path)
    out = tmp_path / "report.json"
    run_tool(binary, case_dir, out)
    actual = json.loads(out.read_text())
    assert_report(actual, expected_report(case_dir))
    assert [m["case_id"] for m in actual["matches"]] == ["alpha-patrol", "beta-swap", "delta-indent", "gamma-echo"]


def test_dynamic_portal_dash_echo_and_conflicts(binary, tmp_path):
    case_dir = tmp_path / "fresh"
    write_case(
        case_dir,
        "container-name-does-not-match.flux",
        """
        case_id omega-rift
        rows 6
        cols 8
        rounds 6
        grid
        ########
        #..0..E#
        #.H#...#
        #..0...#
        #......#
        ########
        end_grid
        actors
        C 4 1 5 3
        A 4 2 4 1
        B 4 3 4 2
        end_actors
        commands
        A E E DN E WST W
        B WST N DE WST W W
        C DE N WST E E W
        end_commands
        """,
    )
    write_case(
        case_dir,
        "zeta.flux",
        """
        case_id alpha-before-omega
        rows 5
        cols 6
        rounds 4
        grid
        ######
        #E...#
        #.H..#
        #....#
        ######
        end_grid
        actors
        X 3 1 2 2
        Y 3 2 2 1
        end_actors
        commands
        X E N N W
        Y WST N E W
        end_commands
        """,
    )
    out = tmp_path / "nested" / "report.json"
    run_tool(binary, case_dir, out)
    actual = json.loads(out.read_text())
    expected = expected_report(case_dir)
    assert_report(actual, expected)
    assert [m["case_id"] for m in actual["matches"]] == ["alpha-before-omega", "omega-rift"]
    assert any(":portal:0" in event or ":echo" in event or ":bump:" in event for m in actual["matches"] for event in m["events"])
    assert "container-name-does-not-match" not in json.dumps(actual)


def test_max_rounds_changes_state_score_and_summary_digest(binary, tmp_path):
    case_dir = copy_bundled(tmp_path)
    full_out = tmp_path / "full.json"
    capped_out = tmp_path / "capped.json"
    run_tool(binary, case_dir, full_out)
    run_tool(binary, case_dir, capped_out, ["--max-rounds", "2"])
    full = json.loads(full_out.read_text())
    capped = json.loads(capped_out.read_text())
    assert_report(capped, expected_report(case_dir, max_rounds=2))
    assert capped != full
    assert capped["summary"]["digest"] != full["summary"]["digest"]
    assert {match["rounds_completed"] for match in capped["matches"]} == {2}


def test_dynamic_swap_and_iterative_blocking(binary, tmp_path):
    case_dir = tmp_path / "cases"
    write_case(
        case_dir,
        "swap.flux",
        """
        case_id swap-cycle-check
        rows 5
        cols 7
        rounds 5
        grid
        #######
        #.....#
        #..E..#
        #.....#
        #######
        end_grid
        actors
        A 2 2 3 5
        B 2 3 3 4
        C 2 4 3 1
        D 3 4 1 2
        end_actors
        commands
        A E E E W W
        B WST WST E W W
        C WST WST WST W W
        D N N WST W W
        end_commands
        """,
    )
    out = tmp_path / "report.json"
    run_tool(binary, case_dir, out)
    actual = json.loads(out.read_text())
    expected = expected_report(case_dir)
    assert_report(actual, expected)
    events = actual["matches"][0]["events"]
    assert any(":blocked:" in event for event in events)
    assert any(":bump:" in event for event in events)


def test_dynamic_hazard_down_exit_and_tired_events(binary, tmp_path):
    case_dir = tmp_path / "cases"
    write_case(
        case_dir,
        "hazard.flux",
        """
        case_id hazard-ledger
        rows 5
        cols 7
        rounds 5
        grid
        #######
        #..H.E#
        #.....#
        #.....#
        #######
        end_grid
        actors
        A 1 1 2 1
        B 3 1 1 2
        end_actors
        commands
        A E E E E W
        B DE DE N E W
        end_commands
        """,
    )
    out = tmp_path / "report.json"
    run_tool(binary, case_dir, out)
    actual = json.loads(out.read_text())
    expected = expected_report(case_dir)
    assert_report(actual, expected)
    event_text = "|".join(actual["matches"][0]["events"])
    assert "hazard" in event_text
    assert "exit" in event_text or "down" in event_text or "tired" in event_text


def test_dynamic_gate_charge_and_turret_state_machine(binary, tmp_path):
    case_dir = tmp_path / "cases"
    write_case(
        case_dir,
        "not-the-id.flux",
        """
        case_id gate-charge-laser
        rows 7
        cols 9
        rounds 7
        grid
        #########
        #..G..E.#
        #..#....#
        #.P+..T.#
        #.......#
        #.......#
        #########
        end_grid
        actors
        A 4 2 3 2
        B 4 3 2 1
        C 1 2 5 3
        end_actors
        commands
        A N N E E E E W
        B N W W W W W W
        C E W W W W W W
        end_commands
        """,
    )
    out = tmp_path / "report.json"
    run_tool(binary, case_dir, out)
    actual = json.loads(out.read_text())
    expected = expected_report(case_dir)
    assert_report(actual, expected)
    events = "|".join(actual["matches"][0]["events"])
    assert "gate" in events
    assert "gate_open" in events
    assert "charge" in events
    assert "laser" in events
    assert actual["matches"][0]["digest"] == expected["matches"][0]["digest"]


def test_round_cap_preserves_gate_prefix_and_laser_absence(binary, tmp_path):
    case_dir = tmp_path / "cases"
    write_case(
        case_dir,
        "gated.flux",
        """
        case_id prefix-gate-audit
        rows 6
        cols 8
        rounds 6
        grid
        ########
        #..G.E.#
        #.P+T..#
        #......#
        #......#
        ########
        end_grid
        actors
        A 4 2 5 1
        B 4 4 4 2
        end_actors
        commands
        A N N E N E W
        B N WST WST E E W
        end_commands
        """,
    )
    full_out = tmp_path / "full.json"
    cap_out = tmp_path / "cap.json"
    run_tool(binary, case_dir, full_out)
    run_tool(binary, case_dir, cap_out, ["--max-rounds", "3"])
    full = json.loads(full_out.read_text())
    cap = json.loads(cap_out.read_text())
    assert_report(full, expected_report(case_dir))
    assert_report(cap, expected_report(case_dir, max_rounds=3))
    assert full["summary"]["digest"] != cap["summary"]["digest"]
    assert cap["matches"][0]["rounds_completed"] == 3
    assert "gate_open" in "|".join(cap["matches"][0]["events"])


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        (
            """
            case_id bad-portal
            rows 3
            cols 5
            rounds 1
            grid
            #####
            #0..#
            #####
            end_grid
            actors
            A 1 2 1 1
            end_actors
            commands
            A W
            end_commands
            """,
            "portal",
        ),
        (
            """
            case_id bad-command
            rows 3
            cols 5
            rounds 1
            grid
            #####
            #...#
            #####
            end_grid
            actors
            A 1 2 1 1
            end_actors
            commands
            A WEST
            end_commands
            """,
            "command",
        ),
    ],
)
def test_invalid_cases_exit_two_delete_stale_output(binary, tmp_path, body, needle):
    case_dir = tmp_path / "cases"
    write_case(case_dir, "bad.flux", body)
    out = tmp_path / "report.json"
    out.write_text("stale")
    proc = run_tool(binary, case_dir, out, check=False)
    assert proc.returncode == 2
    assert not out.exists()
    assert "invalid" in proc.stderr.lower() or "error" in proc.stderr.lower()
    assert needle in proc.stderr.lower()


def test_unknown_option_and_bad_round_cap_are_atomic(binary, tmp_path):
    case_dir = copy_bundled(tmp_path)
    out = tmp_path / "report.json"
    out.write_text("old")
    proc = run_tool(binary, case_dir, out, ["--max-rounds", "0"], check=False)
    assert proc.returncode == 2
    assert not out.exists()
    out.write_text("old")
    proc = run_tool(binary, case_dir, out, ["--bogus", "x"], check=False)
    assert proc.returncode == 2
    assert not out.exists()
