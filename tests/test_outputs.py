import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
INPUT = APP / "input" / "match.json"
OUTPUT = APP / "output" / "report.json"
BIN = APP / "abalone"
PUBLIC_SHA256 = "9c25e54655c2aecc2845f2326ab43ed182c3473728ce8a24cd729218f9397a72"

EXPECTED_REPORT_SHA256 = {
    "public": "03aef5a38cc0fe52cdbb05ec2bfd3054699933feb99078981db83230edff8663",
    "empty-radius-two": "dde87f9bd62872639b02f38b476d82d303a39c6694c7ed7d5e54063210861ea2",
    "validation-precedence": "d564e9d9cfd60037204fe58e46711565316fa956a722be3140af9df05e00cbfa",
    "noncollinear-and-gap": "8c561f0416b6f9d13a0a8e83a39ac310a83dfdaf73d1c0605ca4d5b65e520207",
    "sidestep-matrix": "c3107e37900860cf25b5f9b3d660fc3e70772802039af7c192b28c6092cb28b7",
    "broadside-edge-priority": "4d8d5680615ae7afd1da340c92c25c7c382f98b0f528472a4b36bd86074f5fcb",
    "inline-rejections": "2b05835fdc78a443a880fdcd1ec4ed36210281341d0cee3ed66aa2c3a4a77c6e",
    "push-blocked-behind": "98653443708f72cf31719a99b6fc007b095bb805b2a07f38f730f7061f925b1d",
    "three-push-two": "f47f3188ce486ff0116acf137830ea9203aa8b30ac2534d0868f10b4c0e1ce58",
    "ejection-win-postgame": "f9ba05311443bffaf59747bb8b8a5fa5605af0a7ea7e168aed60ab17bfbaf77c",
    "repetition-three": "ee1efc4eeb9d3299665f2974fc3a1908dbaa868439feb5ec3dd0be64d08803ac",
    "repetition-before-no-progress": "73fcd18de0799bf1b05fb8808ed92b66081f96e5998fae5f9b7e44c7d6ce475f",
    "no-progress-before-move-limit": "195cfac9063f6140f9a28c5f1960f7cbe60b548986e1047170aecc3629e0422b",
    "move-limit-only": "f0e856e37433a6cd018d29a7a7e2e6841fac57291b65e0e12fb5eb985cdbbb5f",
    "max-group-two": "8b4d4be55e52e8ebbfc3449def93df9c5b00daed64a2580e4704586e7c63208f",
    "no-progress-reset-by-ejection": "91e4776d16ec8c1b5f24b3c40b51357ca02dbf6703bb33fe378c85a3fc491d21",
    "exact-ko-rolls-back-turn": "b4fc83f9cfe4a2171d62536d06cf92e48d2df3e6bce55da7a5375f95c60fbd2c",
    "rotation-ko": "f4ea649f98845ce2a26b020f30f6bc43063d49babd4fcef0e84ce2dba6185fcc",
    "rotation-outside-ko-window": "ff5840196d4150ce73e38a5ec90a2e23ddf639db799b2072e70bd0a036f77306",
    "dihedral-ko": "227153ed2ecbe480b1a2df8879ccbf8a4370f918bc1035fec8b0c42a93591fdb",
    "dihedral-repetition-draw": "7018110537d35d2668fcf2f5c0699a15b2dd83a1e0368626225c2b52574c51a8",
    "continuation-forced-ejection": "7b845c57b28297e5c6ecd33cd023b734771f0456d86c6cc2a26738884cc6d84a",
    "continuation-margin-player0": "f99bba9cc0111a44ccd46b3b3ee2afd745eb4543507bc4ab08a4b366fa598bea",
    "continuation-margin-player1": "f5e69ec2cc09c5aa18f9429ae74c77d9d627f9d1ade1bf81caa036a14b4873b5",
    "cooldown-validation-aging": "0e43dadbbc3917d6e78218b3cf9839536360434715fa249db2055432412ed109",
    "cooldown-pushed": "716c6695195fa9f9a2fe1f850ef0869be920c8e4fde18be66d903bcc84134e12",
    "cooldown-ejected": "6bacb4e363a0992d25938911ac7a556adebba8bf0372e0280a053b5328349df0",
    "cooldown-ko-rollback": "da5c9c7435f217b313e04c2cae127dc394e962ce61d66785e256155a14c4ef95",
    "cooldown-breaks-rotation-ko": "d36961151f8adbb6f7e62a25194e10c44e96ac4df8c00e59d057448a658cd508",
    "cooldown-stalled": "9394bc3d918cf300cebc81526b71445dcb10cdce7a3c95d3f95e51fb310022ad",
    "momentum-gain-spend": "0a3d3888fd32304d5e68f880decbac30a978867086c0228b309e717597fa3c09",
    "momentum-breaks-rotation-ko": "7523429433fcd1209cef0d2cc4b94b5ee99e5f95aa2f0163991147639eb5b218",
    "momentum-saturated-rotation-ko": "e13bcd9395d76fb9cb68cd5ae4da99ceec827ee2bacc6847acbc4c64b0c0e209",
    "quiescence-push-horizon": "9f1a3de914b447e998087df60686114b142cdb63bc7ad544945ed053eaea45ef",
    "quiescence-momentum-gate": "3f28c474a6c9de4a465d2db9181ff05a8e43def597a84afec4ac06b173859b67",
    "continuation-momentum-player0": "e5b30c0e21a79662160cbe4ad5fc841675ac9ee5be494b22da6f53f29147de00",
    "continuation-momentum-player1": "efba3b700bc7c889dea9f9ccfe0d58c70b620909961b31dd713bfa6c43b79cd0",
}

def make_case(
    marbles,
    moves,
    *,
    players=("black", "white"),
    radius=3,
    max_group=3,
    target=6,
    repetition=0,
    repetition_equivalence="exact",
    ko_window=0,
    no_progress=0,
    move_limit=0,
    continuation=2,
    quiescence=0,
    tempo_cooldown=0,
    momentum_cap=0,
    momentum=None,
    cooldowns=None,
    next_player=None,
    scores=None,
):
    players = list(players)
    return {
        "players": players,
        "rules": {
            "radius": radius,
            "max_group": max_group,
            "target_ejections": target,
            "repetition_limit": repetition,
            "repetition_equivalence": repetition_equivalence,
            "ko_window": ko_window,
            "no_progress_limit": no_progress,
            "move_limit": move_limit,
            "continuation_depth": continuation,
            "quiescence_depth": quiescence,
            "tempo_cooldown": tempo_cooldown,
            "momentum_cap": momentum_cap,
        },
        "initial": {
            "next_player": next_player or players[0],
            "ejections": scores or {players[0]: 0, players[1]: 0},
            "momentum": momentum or {players[0]: 0, players[1]: 0},
            "cooldowns": [
                {"q": q, "r": r, "player": player, "remaining": remaining}
                for q, r, player, remaining in (cooldowns or [])
            ],
            "marbles": [
                {"q": q, "r": r, "player": player}
                for q, r, player in marbles
            ],
        },
        "moves": moves,
    }


def mv(mid, player, cells, direction):
    return {"id": mid, "player": player, "marbles": cells, "direction": direction}


def hidden_cases():
    cases = {}
    cases["empty-radius-two"] = make_case(
        [(-2, 0, "black"), (2, 0, "white")], [], radius=2, continuation=4
    )
    cases["validation-precedence"] = make_case(
        [(-2, 0, "black"), (-1, 0, "black"), (0, 0, "black"), (1, 0, "white")],
        [
            mv("wrong-before-empty", "white", [], "E"),
            mv("empty", "black", [], "E"),
            mv("too-many", "black", [[-2, 0], [-1, 0], [0, 0], [0, 0]], "E"),
            mv("duplicate", "black", [[-1, 0], [-1, 0]], "E"),
            mv("not-owned", "black", [[1, 0], [1, -1]], "E"),
            mv("not-collinear", "black", [[-2, 0], [-1, 0], [0, 0]], "NE"),
        ],
        max_group=3,
    )
    cases["noncollinear-and-gap"] = make_case(
        [(-2, 0, "black"), (0, 0, "black"), (0, 1, "black"), (2, -1, "white")],
        [
            mv("bent", "black", [[-2, 0], [0, 0], [0, 1]], "E"),
            mv("gap", "black", [[0, 0], [-2, 0]], "E"),
        ],
    )
    cases["sidestep-matrix"] = make_case(
        [(-1, 0, "black"), (0, 0, "black"), (0, -1, "white"), (2, -1, "white")],
        [
            mv("occupied-broadside", "black", [[0, 0], [-1, 0]], "NE"),
            mv("valid-broadside", "black", [[0, 0], [-1, 0]], "SE"),
            mv("white-single", "white", [[2, -1]], "W"),
        ],
    )
    cases["broadside-edge-priority"] = make_case(
        [(0, -3, "black"), (1, -3, "black"), (0, -2, "white")],
        [mv("edge", "black", [[1, -3], [0, -3]], "NE")],
    )
    cases["inline-rejections"] = make_case(
        [(-3, 0, "black"), (-1, 0, "black"), (0, 0, "black"), (1, 0, "white"), (2, 0, "white")],
        [
            mv("own-off", "black", [[-3, 0]], "W"),
            mv("own-block", "black", [[-1, 0]], "E"),
            mv("weak", "black", [[-1, 0], [0, 0]], "E"),
        ],
    )
    cases["push-blocked-behind"] = make_case(
        [(-2, 0, "black"), (-1, 0, "black"), (0, 0, "white"), (1, 0, "black"), (2, -1, "white")],
        [mv("sandwich", "black", [[-1, 0], [-2, 0]], "E")],
    )
    cases["three-push-two"] = make_case(
        [(-3, 0, "black"), (-2, 0, "black"), (-1, 0, "black"), (0, 0, "white"), (1, 0, "white")],
        [mv("sumito", "black", [[-1, 0], [-3, 0], [-2, 0]], "E")],
    )
    cases["ejection-win-postgame"] = make_case(
        [(0, 0, "ember"), (1, 0, "ember"), (2, 0, "frost")],
        [
            mv("winning-ejection", "ember", [[1, 0], [0, 0]], "E"),
            mv("ignored-shape", "frost", [], "NW"),
        ],
        players=("ember", "frost"),
        radius=2,
        scores={"ember": 1, "frost": 0},
        target=2,
    )
    cycle_moves = [
        mv("b1", "black", [[-1, -1]], "E"),
        mv("w1", "white", [[1, 1]], "W"),
        mv("b2", "black", [[0, -1]], "W"),
        mv("w2", "white", [[0, 1]], "E"),
    ]
    cases["repetition-three"] = make_case(
        [(-1, -1, "black"), (1, 1, "white")],
        cycle_moves + copy.deepcopy(cycle_moves) + [mv("after", "black", [[-1, -1]], "E")],
        repetition=3,
        no_progress=20,
        move_limit=20,
    )
    cases["repetition-before-no-progress"] = make_case(
        [(-1, -1, "black"), (1, 1, "white")],
        cycle_moves,
        repetition=2,
        no_progress=4,
        move_limit=4,
    )
    cases["no-progress-before-move-limit"] = make_case(
        [(-2, -1, "black"), (2, 1, "white")],
        [
            mv("a", "black", [[-2, -1]], "E"),
            mv("b", "white", [[2, 1]], "W"),
        ],
        no_progress=2,
        move_limit=2,
    )
    cases["move-limit-only"] = make_case(
        [(-2, -1, "black"), (2, 1, "white")],
        [
            mv("a", "black", [[-2, -1]], "E"),
            mv("b", "white", [[2, 1]], "W"),
            mv("post", "black", [[-1, -1]], "W"),
        ],
        move_limit=2,
    )
    cases["max-group-two"] = make_case(
        [(-2, 1, "red"), (-1, 1, "red"), (0, 1, "red"), (1, 0, "blue")],
        [
            mv("limit", "red", [[-2, 1], [-1, 1], [0, 1]], "E"),
            mv("axis-s", "red", [[-1, 1], [0, 1]], "NE"),
            mv("blue", "blue", [[1, 0]], "SE"),
        ],
        players=("red", "blue"),
        radius=2,
        max_group=2,
    )
    cases["no-progress-reset-by-ejection"] = make_case(
        [(-2, -1, "black"), (1, 0, "black"), (2, 0, "black"), (3, 0, "white"), (2, -1, "white")],
        [
            mv("quiet", "black", [[-2, -1]], "E"),
            mv("white-quiet", "white", [[2, -1]], "W"),
            mv("eject", "black", [[2, 0], [1, 0]], "E"),
        ],
        no_progress=3,
    )
    cases["exact-ko-rolls-back-turn"] = make_case(
        [(-1, -1, "black"), (1, 1, "white")],
        [
            mv("b-out", "black", [[-1, -1]], "E"),
            mv("w-out", "white", [[1, 1]], "W"),
            mv("b-back", "black", [[0, -1]], "W"),
            mv("w-repeat", "white", [[0, 1]], "E"),
            mv("w-alternate", "white", [[0, 1]], "NW"),
        ],
        ko_window=4,
        continuation=4,
    )
    rotation_moves = [
        mv("rotate-black", "black", [[-1, 0]], "NE"),
        mv("rotate-white", "white", [[1, 0]], "SW"),
    ]
    cases["rotation-ko"] = make_case(
        [(-1, 0, "black"), (1, 0, "white")],
        rotation_moves,
        repetition_equivalence="rotations",
        ko_window=2,
    )
    cases["rotation-outside-ko-window"] = make_case(
        [(-1, 0, "black"), (1, 0, "white")],
        rotation_moves,
        repetition_equivalence="rotations",
        ko_window=1,
        continuation=4,
    )
    reflection_moves = [
        mv("reflect-black", "black", [[0, 1]], "NE"),
        mv("reflect-white", "white", [[-1, 0]], "NE"),
    ]
    cases["dihedral-ko"] = make_case(
        [(0, 1, "black"), (-1, 0, "white")],
        reflection_moves,
        repetition_equivalence="dihedral",
        ko_window=2,
    )
    cases["dihedral-repetition-draw"] = make_case(
        [(0, 1, "black"), (-1, 0, "white")],
        reflection_moves + [mv("after-draw", "black", [[1, 0]], "W")],
        repetition=2,
        repetition_equivalence="dihedral",
    )
    cases["continuation-forced-ejection"] = make_case(
        [(0, 0, "black"), (1, 0, "black"), (2, 0, "white"), (-1, 1, "white")],
        [],
        radius=2,
        target=1,
        continuation=3,
    )
    cases["continuation-margin-player0"] = make_case(
        [(0, 0, "black"), (1, 0, "black"), (2, 0, "white"), (-1, 1, "white")],
        [],
        radius=2,
        target=3,
        continuation=1,
    )
    cases["continuation-margin-player1"] = make_case(
        [(0, 0, "white"), (1, 0, "white"), (2, 0, "black"), (-1, 1, "black")],
        [],
        radius=2,
        target=3,
        continuation=1,
        next_player="white",
    )
    cases["cooldown-validation-aging"] = make_case(
        [
            (-2, 0, "black"),
            (0, 0, "black"),
            (2, -1, "white"),
            (1, 1, "white"),
        ],
        [
            mv("still-cooling", "black", [[-2, 0]], "E"),
            mv("age-on-accept", "black", [[0, 0]], "NE"),
            mv("white-quiet", "white", [[1, 1]], "W"),
            mv("cooled", "black", [[-2, 0]], "E"),
            mv("white-again", "white", [[2, -1]], "NW"),
            mv("remaining-one", "black", [[1, -1]], "W"),
        ],
        radius=2,
        tempo_cooldown=2,
        cooldowns=[(-2, 0, "black", 1)],
        continuation=3,
    )
    cases["cooldown-pushed"] = make_case(
        [
            (-2, 0, "white"),
            (-1, 0, "white"),
            (0, 0, "black"),
            (0, 1, "black"),
        ],
        [
            mv("push-annotation", "white", [[-1, 0], [-2, 0]], "E"),
            mv("moved-lock", "black", [[1, 0]], "W"),
            mv("age-other", "black", [[0, 1]], "SE"),
        ],
        players=("black", "white"),
        radius=2,
        next_player="white",
        tempo_cooldown=2,
        cooldowns=[(0, 0, "black", 2)],
        continuation=3,
    )
    cases["cooldown-ejected"] = make_case(
        [
            (0, 0, "white"),
            (1, 0, "white"),
            (2, 0, "black"),
            (-1, 1, "black"),
        ],
        [
            mv("eject-cooling", "white", [[1, 0], [0, 0]], "E"),
            mv("survivor", "black", [[-1, 1]], "E"),
        ],
        players=("black", "white"),
        radius=2,
        next_player="white",
        target=3,
        tempo_cooldown=2,
        cooldowns=[(2, 0, "black", 2)],
        continuation=3,
    )
    cooldown_cycle = [
        mv("black-a-out", "black", [[-2, -1]], "E"),
        mv("white-c-out", "white", [[2, 1]], "W"),
        mv("black-b-out", "black", [[-2, 1]], "E"),
        mv("white-d-out", "white", [[2, -1]], "W"),
        mv("black-a-back", "black", [[-1, -1]], "W"),
        mv("white-c-back", "white", [[1, 1]], "E"),
        mv("black-b-back", "black", [[-1, 1]], "W"),
        mv("white-d-repeat", "white", [[1, -1]], "E"),
        mv("white-d-alternate", "white", [[1, -1]], "NW"),
    ]
    cases["cooldown-ko-rollback"] = make_case(
        [
            (-2, -1, "black"),
            (-2, 1, "black"),
            (2, 1, "white"),
            (2, -1, "white"),
        ],
        cooldown_cycle,
        radius=3,
        ko_window=8,
        tempo_cooldown=1,
        cooldowns=[
            (-2, 1, "black", 1),
            (2, -1, "white", 1),
        ],
        continuation=3,
    )
    cases["cooldown-breaks-rotation-ko"] = make_case(
        [(-1, 0, "black"), (1, 0, "white")],
        rotation_moves,
        repetition_equivalence="rotations",
        ko_window=2,
        tempo_cooldown=1,
        continuation=3,
    )
    cases["cooldown-stalled"] = make_case(
        [(0, 0, "black"), (2, 0, "white")],
        [],
        radius=2,
        tempo_cooldown=2,
        cooldowns=[(0, 0, "black", 2)],
        continuation=4,
    )
    cases["momentum-gain-spend"] = make_case(
        [
            (-2, 0, "black"),
            (-1, 0, "black"),
            (-2, 1, "black"),
            (0, 0, "white"),
            (2, -1, "white"),
        ],
        [
            mv("unfunded-push", "black", [[-2, 0], [-1, 0]], "E"),
            mv("black-charge", "black", [[-2, 1]], "E"),
            mv("white-charge", "white", [[2, -1]], "W"),
            mv("funded-push", "black", [[-2, 0], [-1, 0]], "E"),
        ],
        radius=2,
        momentum_cap=3,
        continuation=3,
        quiescence=1,
    )
    cases["momentum-breaks-rotation-ko"] = make_case(
        [(-1, 0, "black"), (1, 0, "white")],
        rotation_moves,
        repetition_equivalence="rotations",
        ko_window=2,
        momentum_cap=2,
        continuation=3,
        quiescence=1,
    )
    cases["momentum-saturated-rotation-ko"] = make_case(
        [(-1, 0, "black"), (1, 0, "white")],
        rotation_moves + [mv("white-alternate", "white", [[0, 1]], "NW")],
        repetition_equivalence="rotations",
        ko_window=2,
        momentum_cap=1,
        momentum={"black": 1, "white": 1},
        continuation=3,
        quiescence=1,
    )
    cases["quiescence-push-horizon"] = make_case(
        [
            (0, 0, "black"),
            (1, 0, "black"),
            (2, 0, "white"),
            (-1, 1, "white"),
        ],
        [],
        radius=2,
        target=2,
        momentum_cap=3,
        momentum={"black": 2, "white": 0},
        continuation=0,
        quiescence=2,
    )
    cases["quiescence-momentum-gate"] = make_case(
        [
            (0, 0, "black"),
            (1, 0, "black"),
            (2, 0, "white"),
            (-1, 1, "white"),
        ],
        [],
        radius=2,
        target=2,
        momentum_cap=3,
        continuation=0,
        quiescence=2,
    )
    cases["continuation-momentum-player0"] = make_case(
        [
            (-1, 0, "black"),
            (0, 0, "black"),
            (1, 0, "black"),
            (0, 2, "white"),
        ],
        [],
        radius=2,
        momentum_cap=3,
        momentum={"black": 0, "white": 1},
        continuation=1,
        quiescence=1,
    )
    cases["continuation-momentum-player1"] = make_case(
        [
            (-1, 0, "white"),
            (0, 0, "white"),
            (1, 0, "white"),
            (0, 2, "black"),
        ],
        [],
        radius=2,
        next_player="white",
        momentum_cap=3,
        momentum={"black": 1, "white": 0},
        continuation=1,
        quiescence=1,
    )
    return cases

@pytest.fixture(autouse=True)
def preserve_public_input():
    """Give every test an independent input and restore it afterward."""
    original = INPUT.read_bytes()
    yield
    INPUT.write_bytes(original)


def canonical_report_digest(report):
    encoded = json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_case(name, case):
    INPUT.write_text(json.dumps(case, separators=(",", ":")))
    input_digest = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text('{"stale":true}')
    completed = subprocess.run(
        [str(BIN)],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest() == input_digest
    assert OUTPUT.is_file() and not OUTPUT.is_symlink(), (
        "program did not replace /app/output/report.json with a regular file"
    )
    try:
        actual = json.loads(OUTPUT.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        pytest.fail(f"report.json is not valid JSON: {exc}")
    assert canonical_report_digest(actual) == EXPECTED_REPORT_SHA256[name]


def test_public_input_integrity_and_go_artifact():
    """Preserve the public evidence and require the verifier-built Go binary."""
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest() == PUBLIC_SHA256
    assert BIN.is_file() and BIN.read_bytes()[:4] == b"\x7fELF"


def test_public_match():
    """Replay the supplied match against its frozen canonical commitment."""
    run_case("public", json.loads(INPUT.read_text()))


@pytest.mark.parametrize("name", sorted(hidden_cases()))
def test_compatible_match_matrix(name):
    """Check adversarial replays against offline canonical commitments."""
    run_case(name, hidden_cases()[name])
