"""Named independent checks for the pinned native Kyoto Shogi arena."""

from __future__ import annotations

import json
import os
import re
import socket
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from kyoto_shogi_rules import (
    BLACK as UPPER_SIDE,
)
from kyoto_shogi_rules import (
    CANONICAL_START_FEN,
    DROP_UCI_PATTERN,
    NORMAL_UCI_PATTERN,
    START_FEN,
    Board,
    Move,
    Outcome,
    fen_from_pieces,
)
from kyoto_shogi_rules import (
    WHITE as LOWER_SIDE,
)

PROTOCOL = "arena-kyoto-shogi-v1"
VARIANT = "kyotoshogi"
WIRE_BANNER = b"FAIRY_ARENA_WIRE_V1"
HASH_PATTERN = re.compile(r"[0-9a-f]{16}\Z")
STATE_FIELDS = frozenset(
    {
        "protocol",
        "variant",
        "player_color",
        "start_fen",
        "fen",
        "position_hash",
        "board",
        "turn",
        "result",
        "winner",
        "termination",
        "ply_count",
        "postgame_player_requests",
        "last_move",
        "legal_moves",
        "holdings",
    }
)
MOVE_FIELDS = frozenset(
    {"ply", "actor", "color", "uci", "san", "fen_after", "hash_after"}
)
TRANSCRIPT_FIELDS = frozenset(
    {"ok", "state", "protocol", "variant", "start_fen", "moves"}
)
PUBLIC_FOR_MODEL = {UPPER_SIDE: "white", LOWER_SIDE: "black"}


def run_client(*arguments: str) -> tuple[subprocess.CompletedProcess[str], Any | None]:
    """Run the public native client and parse JSON when emitted."""
    completed = subprocess.run(
        ["/app/arena", "--json", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout) if completed.stdout.strip() else None
    return completed, payload


def successful_transcript() -> dict[str, Any]:
    """Fetch one successful authoritative transcript envelope."""
    completed, payload = run_client("transcript")
    assert completed.returncode == 0, completed.stderr
    assert isinstance(payload, dict)
    assert payload.get("ok") is True
    return payload


def fingerprint(value: Any) -> str:
    """Serialize public state deterministically for mutation checks."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def raw_request(payload: bytes) -> bytes:
    """Send one root-owned raw socket payload for framing checks."""
    path = os.environ.get("ARENA_SOCKET", "/run/arena/arena.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(15)
        connection.connect(path)
        connection.sendall(payload)
        connection.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class Replay:
    """Independent final position and classification for a transcript."""

    board: Board
    outcome: Outcome
    resigned: bool


def replay_transcript(payload: dict[str, Any]) -> Replay:
    """Replay all accepted actions with verifier-owned Kyoto Shogi rules."""
    assert payload["start_fen"] == START_FEN
    board = Board.from_fen(CANONICAL_START_FEN)
    resigned = False
    records = payload["moves"]
    for index, record in enumerate(records):
        assert set(record) == MOVE_FIELDS
        assert record["ply"] == index + 1
        expected_color = PUBLIC_FOR_MODEL[board.turn]
        assert record["color"] == expected_color
        assert record["actor"] == (
            "player" if expected_color == "white" else "opponent"
        )
        token = record["uci"]
        if token == "resign":
            assert index == len(records) - 1
            assert expected_color == "white"
            assert record["fen_after"] == board.fen()
            resigned = True
            continue
        assert token in board.legal_moves()
        applied = board.push(token)
        assert record["fen_after"] == applied.fen_after
        assert HASH_PATTERN.fullmatch(record["hash_after"])
        assert isinstance(record["san"], str) and record["san"]
        if board.outcome().finished:
            assert index == len(records) - 1
    outcome = (
        Outcome("white_win", LOWER_SIDE, "resignation")
        if resigned
        else board.outcome()
    )
    return Replay(board, outcome, resigned)


@pytest.fixture(scope="session")
def transcript() -> dict[str, Any]:
    """Provide the live authoritative transcript to named checks."""
    return successful_transcript()


@pytest.fixture(scope="session")
def replayed(transcript: dict[str, Any]) -> Replay:
    """Provide the independently replayed final state."""
    return replay_transcript(transcript)


def test_readme_documents_complete_kyoto_shogi_and_stopping_contract() -> None:
    """Require commands, Kyoto Shogi rules, endings, schemas, and stopping."""
    readme = Path("/app/README.md").read_text(encoding="utf-8")
    lowered = " ".join(readme.lower().split())
    for command in (
        "/app/arena status",
        "/app/arena move MOVE",
        "/app/arena resign",
        "/app/arena transcript",
    ):
        assert command in readme
    for phrase in (
        "5-by-5",
        "files are `a` through `e`",
        "must flip it to the other face",
        "there is no promotion zone",
        "`+p` is a rook",
        "`+s` is a bishop",
        "`+n` moves as a gold",
        "with either face",
        "no nifu, uchifuzume",
        "fourth occurrence",
        "having no legal move while not checked is also a loss",
        "one arena command at a time",
        "send no more arena requests",
        "checkmate",
    ):
        assert phrase in lowered
    for field in STATE_FIELDS | MOVE_FIELDS | {"ok", "error", "code", "message"}:
        assert re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", readme)
    assert "oracle" not in lowered and "verifier" not in lowered


def test_transcript_uses_exact_versioned_json_schemas(transcript: dict[str, Any]) -> None:
    """Require exact transcript, state, action schemas and strict scalar types."""
    assert set(transcript) == TRANSCRIPT_FIELDS
    assert transcript["ok"] is True
    state = transcript["state"]
    assert set(state) == STATE_FIELDS
    for record in transcript["moves"]:
        assert set(record) == MOVE_FIELDS
        assert type(record["ply"]) is int and record["ply"] >= 1
        assert HASH_PATTERN.fullmatch(record["hash_after"])
    assert type(state["ply_count"]) is int
    assert type(state["postgame_player_requests"]) is int
    assert state["legal_moves"] == sorted(set(state["legal_moves"]))


def test_protocol_identity_and_opening_are_exact(transcript: dict[str, Any]) -> None:
    """Require the protected arena to identify the pinned Kyoto Shogi session."""
    state = transcript["state"]
    assert transcript["protocol"] == state["protocol"] == PROTOCOL
    assert transcript["variant"] == state["variant"] == VARIANT
    assert transcript["start_fen"] == state["start_fen"] == START_FEN
    assert state["player_color"] == "white"


def test_transcript_strictly_alternates_atomic_white_black_plies(
    transcript: dict[str, Any],
) -> None:
    """Require consecutive player-White and opponent-Black chronology."""
    assert transcript["moves"]
    for index, record in enumerate(transcript["moves"]):
        white_ply = index % 2 == 0
        assert record["ply"] == index + 1
        assert record["actor"] == ("player" if white_ply else "opponent")
        assert record["color"] == ("white" if white_ply else "black")


def test_every_move_replays_under_independent_kyoto_shogi_rules(
    transcript: dict[str, Any], replayed: Replay
) -> None:
    """Require every non-resignation action to be independently legal."""
    assert not replayed.resigned
    for record in transcript["moves"]:
        assert NORMAL_UCI_PATTERN.fullmatch(record["uci"]) or DROP_UCI_PATTERN.fullmatch(record["uci"])
        assert Board.from_fen(record["fen_after"]).fen() == record["fen_after"]


def test_final_public_state_matches_independent_replay(
    transcript: dict[str, Any], replayed: Replay
) -> None:
    """Require final FEN, board, turn, chronology, and legal moves to match."""
    state = transcript["state"]
    board = replayed.board
    assert state["fen"] == board.fen()
    assert state["board"] == board.board_text()
    assert state["turn"] == PUBLIC_FOR_MODEL[board.turn]
    assert state["ply_count"] == len(transcript["moves"])
    assert state["last_move"] == transcript["moves"][-1]
    expected = [] if replayed.outcome.finished else list(board.legal_moves())
    assert state["legal_moves"] == expected
    assert state["position_hash"] == transcript["moves"][-1]["hash_after"]
    exposed = {
        (item["color"], item["piece"]): item["count"]
        for item in state["holdings"]
    }
    expected_holdings = {}
    for model_color, public_color in PUBLIC_FOR_MODEL.items():
        for kind in "NLPS":
            count = board.hand_count(model_color, kind)
            if count:
                piece = kind if public_color == "white" else kind.lower()
                expected_holdings[(public_color, piece)] = count
    assert exposed == expected_holdings


def test_final_result_is_a_genuine_independent_white_win(
    transcript: dict[str, Any], replayed: Replay
) -> None:
    """Pass only an independently reproduced White checkmate."""
    state = transcript["state"]
    assert replayed.outcome.finished and not replayed.resigned
    assert replayed.outcome.winner == UPPER_SIDE
    assert PUBLIC_FOR_MODEL[replayed.outcome.winner] == "white"
    assert replayed.outcome.termination == "checkmate"
    assert state["result"] == "white_win"
    assert state["winner"] == "white"
    assert state["termination"] == replayed.outcome.termination


def test_terminal_win_has_no_legal_moves_or_postgame_player_traffic(
    transcript: dict[str, Any], replayed: Replay
) -> None:
    """Require terminal exposure and clean agent stopping with no queued request."""
    state = transcript["state"]
    assert replayed.outcome.finished
    assert state["legal_moves"] == []
    assert state["postgame_player_requests"] == 0


def test_independent_opening_has_exact_compact_armies_and_moves() -> None:
    """Freeze both five-piece armies and all twelve forced-flip moves."""
    board = Board.from_fen(START_FEN)
    assert board.fen() == CANONICAL_START_FEN
    assert board.count(color=UPPER_SIDE) == board.count(color=LOWER_SIDE) == 5
    assert board.legal_moves() == (
        "a1a2-", "a1b2-", "b1a2+", "b1b2+", "b1c2+", "c1b2",
        "c1c2", "c1d2", "d1c2-", "d1d2-", "d1e2-", "e1e2+",
    )


def test_independent_forced_flips_capture_hands_and_two_face_drops() -> None:
    """Require plus/minus flips, capture identity, and both drop faces."""
    board = Board.from_fen(
        fen_from_pieces({"a1": "K", "e5": "k", "c3": "P", "b3": "+S"})
    )
    assert "c3c4+" in board.legal_moves() and "c3c4" not in board.legal_moves()
    assert all(move.endswith("-") for move in board.legal_moves() if move.startswith("b3"))
    capture = Board.from_fen(
        fen_from_pieces({"a1": "K", "e5": "k", "b2": "+P", "b4": "+s"})
    )
    capture.push("b2b4-")
    assert capture.hand_count(UPPER_SIDE, "S") == 1
    drops = Board.from_fen(
        fen_from_pieces(
            {"a1": "K", "e5": "k"},
            hands={UPPER_SIDE: {"P": 1}},
        )
    )
    assert {"P@c3", "+P@c3", "P@a5", "+P@a5"} <= set(drops.legal_moves())


def test_independent_compact_move_drop_and_promotion_tokens_are_exact() -> None:
    """Require exact board flips and ordinary or promoted at-sign drops."""
    assert Move.from_uci("a1a2-").uci() == "a1a2-"
    assert Move.from_uci("+P@c3").uci() == "+P@c3"
    for malformed in ("a1f2", "a1a6", "P*c3", "p@c3", "a4a5q"):
        assert NORMAL_UCI_PATTERN.fullmatch(malformed) is None
        assert DROP_UCI_PATTERN.fullmatch(malformed) is None


def test_independent_king_safety_and_no_move_losses_are_enforced() -> None:
    """Require king safety plus distinct checked and safe no-move losses."""
    checked = Board.from_fen(
        fen_from_pieces({"a1": "K", "e5": "k", "a5": "+p"})
    )
    assert checked.is_in_check(UPPER_SIDE)
    assert all(not move.startswith("a1a") for move in checked.legal_moves())
    checkmate = Board.from_fen(
        fen_from_pieces({"a1": "K", "a3": "k", "a2": "s"})
    )
    stalemate = Board.from_fen(
        fen_from_pieces({"a1": "K", "a3": "k", "a2": "+s"})
    )
    assert checkmate.outcome() == Outcome("white_win", LOWER_SIDE, "checkmate")
    assert stalemate.outcome() == Outcome("white_win", LOWER_SIDE, "stalemate")


def test_status_and_transcript_expose_identical_authoritative_state(
    transcript: dict[str, Any],
) -> None:
    """Require the flat status object to match the nested transcript state."""
    completed, status = run_client("status")
    assert completed.returncode == 0, completed.stderr
    assert isinstance(status, dict)
    assert set(status) == STATE_FIELDS | {"ok"}
    assert status.pop("ok") is True
    assert status == transcript["state"]


def test_client_and_referee_reject_batch_or_control_surfaces_atomically(
    transcript: dict[str, Any],
) -> None:
    """Require local control-verb rejection and server single-command framing."""
    before = fingerprint(transcript["state"])
    for arguments in (
        ("reset",),
        ("undo",),
        ("analysis",),
        ("engine",),
        ("move", "a2a3", "status"),
        ("resign", "status"),
    ):
        completed, payload = run_client(*arguments)
        assert completed.returncode == 2
        assert payload is None
    response = raw_request(b"status\nstatus\n")
    assert response.startswith(b"FAIL\n" + WIRE_BANNER + b"\n")
    assert b"ERROR\tbad_request\t" in response
    assert fingerprint(successful_transcript()["state"]) == before


def test_terminal_root_probes_are_immutable_game_over_rejections(
    transcript: dict[str, Any],
) -> None:
    """Require postgame root verification to preserve state and full history."""
    before_state = fingerprint(transcript["state"])
    before_moves = transcript["moves"]
    for command in (("move", "a2a3"), ("resign",)):
        completed, payload = run_client(*command)
        assert completed.returncode == 1
        assert isinstance(payload, dict)
        assert payload["error"]["code"] == "game_over"
        assert fingerprint(payload["state"]) == before_state
    after = successful_transcript()
    assert after["moves"] == before_moves
    assert fingerprint(after["state"]) == before_state


def test_provenance_policy_and_private_runtime_surface_are_consistent() -> None:
    """Require exact-source disclosure, explicit weakening, and root-only assets."""
    doc_root = Path("/usr/share/doc/kyoto-shogi-arena")
    source = (doc_root / "fairy-stockfish" / "PROVENANCE.md").read_text(encoding="utf-8")
    policy = (doc_root / "OPPONENT_POLICY.md").read_text(encoding="utf-8")
    native = (doc_root / "arena-native" / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "f3e6969d11d1bec17eba26e7ae0e629ad4af71dd" in source
    assert "There are no other local source changes" in source
    assert "20,000 nodes" in policy and "MultiPV=2" in policy
    assert "100,000 nodes" in policy
    assert "VARIANT" in native and "PROTOCOL" in native
    for path in (
        Path("/opt/arena-private/referee"),
        Path("/opt/arena-private/opponent"),
        Path("/opt/arena-private/difficulty_knobs.conf"),
    ):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode & 0o077 == 0
    assert {path.name for path in Path("/app").iterdir()} == {"README.md", "arena"}
