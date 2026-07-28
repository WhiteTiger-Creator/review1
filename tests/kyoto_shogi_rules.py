"""Independent, verifier-only rules for the pinned Kyoto Shogi arena.

The protected referee and its opponent are deliberately not imported or
invoked here. This module is a compact second implementation of the exact
5-by-5 rules: two-sided pieces that flip after every board move, alternative
drop faces, capture-to-hand, king safety, no-move losses, and repetition.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

BLACK = "black"  # Sente; uppercase FEN pieces; moves first publicly as White.
WHITE = "white"  # Gote; lowercase FEN pieces; moves publicly as Black.
SENTE = BLACK
GOTE = WHITE
COLORS = frozenset((BLACK, WHITE))

START_FEN = "p+nks+l/5/5/5/+LSK+NP[-] w 0 1"
CANONICAL_START_FEN = "p+nks+l/5/5/5/+LSK+NP[] w - - 0 1"

BOARD_FILES = 5
BOARD_RANKS = 5
BOARD_SIZE = BOARD_FILES * BOARD_RANKS
FILES = "abcde"
BASE_TYPES = frozenset("KPNSL")
PROMOTABLE_TYPES = frozenset("PNSL")
HAND_ORDER = "NLPS"
FOURFOLD_OCCURRENCES = 4

NORMAL_UCI_PATTERN = re.compile(r"[a-e][1-5][a-e][1-5][+-]?\Z")
DROP_UCI_PATTERN = re.compile(r"\+?[PNSL]@[a-e][1-5]\Z")

FNV64_OFFSET_BASIS = 14_695_981_039_346_656_037
FNV64_PRIME = 1_099_511_628_211


def opposite(color: str) -> str:
    """Return the opposing public Kyoto Shogi color."""
    if color == BLACK:
        return WHITE
    if color == WHITE:
        return BLACK
    raise ValueError(f"unknown Kyoto Shogi color: {color!r}")


def piece_color(piece: str) -> str:
    """Return Black for uppercase FEN pieces and White for lowercase ones."""
    if not _valid_piece_token(piece):
        raise ValueError(f"unknown Kyoto Shogi piece: {piece!r}")
    return BLACK if piece[-1].isupper() else WHITE


def base_type(piece: str) -> str:
    """Return a board piece's unpromoted uppercase type."""
    if not _valid_piece_token(piece):
        raise ValueError(f"unknown Kyoto Shogi piece: {piece!r}")
    return piece[-1].upper()


def is_promoted(piece: str) -> bool:
    """Return whether a board piece carries the canonical FEN plus prefix."""
    if not _valid_piece_token(piece):
        raise ValueError(f"unknown Kyoto Shogi piece: {piece!r}")
    return piece.startswith("+")


def _valid_piece_token(piece: str) -> bool:
    if len(piece) == 1:
        return piece.upper() in BASE_TYPES
    if len(piece) == 2 and piece[0] == "+":
        return piece[1].upper() in PROMOTABLE_TYPES
    return False


def square_index(square: str) -> int:
    """Convert a canonical UCI square to the top-down FEN scan index."""
    if len(square) != 2 or square[0] not in FILES or square[1] not in "12345":
        raise ValueError(f"invalid UCI square: {square!r}")
    column = FILES.index(square[0])
    rank = BOARD_RANKS - int(square[1])
    return rank * BOARD_FILES + column


def square_name(index: int) -> str:
    """Convert a top-down FEN scan index to a canonical UCI square."""
    if not 0 <= index < BOARD_SIZE:
        raise ValueError(f"invalid Kyoto Shogi square index: {index}")
    rank, column = divmod(index, BOARD_FILES)
    return f"{FILES[column]}{BOARD_RANKS - rank}"


def _coordinates(index: int) -> tuple[int, int]:
    rank, column = divmod(index, BOARD_FILES)
    return column, rank


def _index(file_number: int, rank: int) -> int:
    return rank * BOARD_FILES + file_number


def _on_board(file_number: int, rank: int) -> bool:
    return 0 <= file_number < BOARD_FILES and 0 <= rank < BOARD_RANKS


def _forward(color: str) -> int:
    return -1 if color == BLACK else 1


def fnv1a64(text: str) -> str:
    """Return the lowercase 16-hex FNV-1a-64 digest of exact UTF-8 bytes."""
    value = FNV64_OFFSET_BASIS
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * FNV64_PRIME) & 0xFFFF_FFFF_FFFF_FFFF
    return f"{value:016x}"


@dataclass(frozen=True)
class Move:
    """One canonical UCI board move or hand-piece drop."""

    source: int | None
    target: int
    promote: bool = False
    demote: bool = False
    drop_piece: str | None = None

    @classmethod
    def from_uci(cls, text: str) -> Move:
        """Parse exactly one canonical, case-sensitive UCI move string."""
        if NORMAL_UCI_PATTERN.fullmatch(text) is not None:
            return cls(
                source=square_index(text[:2]),
                target=square_index(text[2:4]),
                promote=text.endswith("+"),
                demote=text.endswith("-"),
            )
        if DROP_UCI_PATTERN.fullmatch(text) is not None:
            face, target = text.split("@", 1)
            return cls(
                source=None,
                target=square_index(target),
                drop_piece=face,
            )
        raise ValueError(f"invalid canonical UCI move: {text!r}")

    @property
    def is_drop(self) -> bool:
        """Return whether this move places a piece from hand."""
        return self.source is None

    def uci(self) -> str:
        """Render this move in exact canonical UCI notation."""
        if self.is_drop:
            if self.drop_piece is None or self.drop_piece.lstrip("+") not in HAND_ORDER:
                raise ValueError("drop move has no valid hand-piece type")
            return f"{self.drop_piece}@{square_name(self.target)}"
        if self.source is None:
            raise AssertionError("non-drop move has no source")
        suffix = "+" if self.promote else "-" if self.demote else ""
        return f"{square_name(self.source)}{square_name(self.target)}{suffix}"


@dataclass(frozen=True)
class AppliedMove:
    """Independently derived facts for one successfully applied board move."""

    uci: str
    color: str
    piece: str
    captured: str | None
    is_drop: bool
    promoted: bool
    gave_check: bool
    fen_after: str
    position_key_after: str
    played_ply_count: int
    position_occurrences: int


@dataclass(frozen=True)
class Outcome:
    """A fully adjudicated arena result."""

    result: str
    winner: str | None
    termination: str | None

    @property
    def finished(self) -> bool:
        """Return whether the result is terminal."""
        return self.result != "ongoing"


class Board:
    """Independent Kyoto Shogi board, hand, history, and adjudication model."""

    def __init__(self, fen: str = CANONICAL_START_FEN) -> None:
        self._squares: list[str | None] = [None] * BOARD_SIZE
        self.hands: dict[str, Counter[str]] = {
            BLACK: Counter(),
            WHITE: Counter(),
        }
        self.turn = BLACK
        self.no_capture_plies = 0
        self.fullmove_number = 1
        self.played_ply_count = 0
        self._position_counts: Counter[str] = Counter()
        self._state_keys: list[str] = []
        self._move_history: list[AppliedMove] = []
        self._forced_outcome: Outcome | None = None
        self._load_fen(fen)
        key = self.position_key()
        self._position_counts[key] = 1
        self._state_keys.append(key)

    @classmethod
    def from_fen(cls, fen: str) -> Board:
        """Construct a board from canonical Fairy-Stockfish Kyoto Shogi FEN."""
        return cls(fen)

    def copy(self, *, include_history: bool = True) -> Board:
        """Return an independent copy, optionally omitting adjudication history."""
        copied = object.__new__(Board)
        copied._squares = self._squares.copy()
        copied.hands = {
            BLACK: self.hands[BLACK].copy(),
            WHITE: self.hands[WHITE].copy(),
        }
        copied.turn = self.turn
        copied.no_capture_plies = self.no_capture_plies
        copied.fullmove_number = self.fullmove_number
        copied.played_ply_count = self.played_ply_count
        copied._forced_outcome = self._forced_outcome
        if include_history:
            copied._position_counts = self._position_counts.copy()
            copied._state_keys = self._state_keys.copy()
            copied._move_history = self._move_history.copy()
        else:
            key = copied.position_key()
            copied._position_counts = Counter({key: 1})
            copied._state_keys = [key]
            copied._move_history = []
            copied._forced_outcome = None
        return copied

    def _load_fen(self, fen: str) -> None:
        if fen == START_FEN:
            fen = CANONICAL_START_FEN
        fields = fen.split(" ")
        if len(fields) != 6 or any(field == "" for field in fields):
            raise ValueError("Kyoto Shogi FEN must contain exactly six fields")
        placement_with_hand, active, castling, en_passant, clock, fullmove = fields
        if castling != "-" or en_passant != "-":
            raise ValueError("Kyoto Shogi castling and en-passant fields must be '-'")
        if active not in {"b", "w"}:
            raise ValueError("Kyoto Shogi FEN active color must be 'b' or 'w'")
        if re.fullmatch(r"[0-9]+", clock) is None or re.fullmatch(
            r"[1-9][0-9]*", fullmove
        ) is None:
            raise ValueError("Kyoto Shogi FEN counters are invalid")
        matched = re.fullmatch(r"(.+)\[([^]]*)\]", placement_with_hand)
        if matched is None:
            raise ValueError("Kyoto Shogi FEN must include bracketed hands")
        placement, hand_field = matched.groups()

        rows = placement.split("/")
        if len(rows) != BOARD_RANKS:
            raise ValueError("Kyoto Shogi FEN must contain exactly five ranks")
        parsed: list[str | None] = [None] * BOARD_SIZE
        for rank, row in enumerate(rows):
            column = 0
            token_index = 0
            previous_was_digit = False
            while token_index < len(row):
                token = row[token_index]
                if token in "123456789":
                    if previous_was_digit:
                        raise ValueError("Kyoto Shogi FEN has a non-canonical empty run")
                    column += int(token)
                    previous_was_digit = True
                    token_index += 1
                    continue
                previous_was_digit = False
                if token == "+":
                    if token_index + 1 >= len(row):
                        raise ValueError("Kyoto Shogi FEN has a dangling promotion marker")
                    piece = row[token_index : token_index + 2]
                    token_index += 2
                else:
                    piece = token
                    token_index += 1
                if not _valid_piece_token(piece):
                    raise ValueError(f"Kyoto Shogi FEN contains unknown piece {piece!r}")
                if column >= BOARD_FILES:
                    raise ValueError("Kyoto Shogi FEN rank contains more than five files")
                parsed[rank * BOARD_FILES + column] = piece
                column += 1
            if column != BOARD_FILES:
                raise ValueError("each Kyoto Shogi FEN rank must contain five files")

        if parsed.count("K") != 1 or parsed.count("k") != 1:
            raise ValueError("Kyoto Shogi FEN must contain exactly one king per side")

        self._squares = parsed
        self.turn = BLACK if active == "w" else WHITE
        self.hands = self._parse_hands(hand_field)
        self.no_capture_plies = int(clock)
        self.fullmove_number = int(fullmove)
        self.played_ply_count = 2 * (self.fullmove_number - 1) + (
            1 if self.turn == WHITE else 0
        )

        if self._placement_field() != placement:
            raise ValueError("Kyoto Shogi FEN board field is not canonical")
        if self._hand_field() != hand_field:
            raise ValueError("Kyoto Shogi FEN hand field is not canonical")

    @staticmethod
    def _parse_hands(field: str) -> dict[str, Counter[str]]:
        hands = {BLACK: Counter(), WHITE: Counter()}
        if field in {"", "-"}:
            return hands
        for symbol in field:
            if symbol not in "NLPSnlps":
                raise ValueError("Kyoto Shogi FEN has an invalid hand token")
            color = BLACK if symbol.isupper() else WHITE
            kind = symbol.upper()
            hands[color][kind] += 1
        return hands

    def _placement_field(self) -> str:
        rows: list[str] = []
        for rank in range(BOARD_RANKS):
            parts: list[str] = []
            empty = 0
            for column in range(BOARD_FILES):
                piece = self._squares[rank * BOARD_FILES + column]
                if piece is None:
                    empty += 1
                    continue
                if empty:
                    parts.append(str(empty))
                    empty = 0
                parts.append(piece)
            if empty:
                parts.append(str(empty))
            rows.append("".join(parts))
        return "/".join(rows)

    def _hand_field(self) -> str:
        tokens: list[str] = []
        for color in (BLACK, WHITE):
            for kind in HAND_ORDER:
                count = self.hands[color][kind]
                token = kind if color == BLACK else kind.lower()
                tokens.extend(token for _ in range(count))
        return "".join(tokens)

    def fen(self) -> str:
        """Return the exact canonical six-field engine FEN for this position."""
        active = "w" if self.turn == BLACK else "b"
        return (
            f"{self._placement_field()}[{self._hand_field()}] {active} - - "
            f"{self.no_capture_plies} {self.fullmove_number}"
        )

    def position_key(self) -> str:
        """Return board, both hands, and side-to-move repetition identity."""
        placement, active, *_ = self.fen().split(" ")
        return f"{placement} {active}"

    @staticmethod
    def normalized_position_key(fen: str) -> str:
        """Normalize a strict FEN to the exact three-field repetition key."""
        return Board(fen).position_key()

    def position_hash(self) -> str:
        """Return FNV-1a-64 over the exact full canonical FEN."""
        return fnv1a64(self.fen())

    def repetition_hash(self) -> str:
        """Return FNV-1a-64 over the exact canonical repetition key."""
        return fnv1a64(self.position_key())

    def position_occurrences(self) -> int:
        """Return how often the current repetition key has occurred."""
        return self._position_counts[self.position_key()]

    def board_text(self) -> str:
        """Render the exact public 5-by-5 board representation."""
        display = {
            "+P": "R", "+p": "r", "+S": "B", "+s": "b",
            "+N": "G", "+n": "g", "+L": "G", "+l": "g",
        }
        rows: list[str] = []
        for rank in range(BOARD_RANKS):
            tokens = [
                display.get(
                    self._squares[rank * BOARD_FILES + column],
                    self._squares[rank * BOARD_FILES + column] or ".",
                )
                for column in range(BOARD_FILES)
            ]
            rows.append(f"{BOARD_RANKS - rank}  " + " ".join(tokens))
        rows.append("   " + " ".join(FILES))
        return "\n".join(rows)

    def piece_at(self, square: str) -> str | None:
        """Return the FEN piece token at one canonical UCI square."""
        return self._squares[square_index(square)]

    def hand_count(self, color: str, kind: str) -> int:
        """Return one side's count of an unpromoted uppercase hand type."""
        if color not in COLORS or kind not in HAND_ORDER:
            raise ValueError("invalid Kyoto Shogi hand lookup")
        return self.hands[color][kind]

    def count(self, *, color: str | None = None, piece: str | None = None) -> int:
        """Count board pieces by color or exact FEN token."""
        if piece is not None:
            return self._squares.count(piece)
        if color is None:
            return sum(item is not None for item in self._squares)
        return sum(
            item is not None and piece_color(item) == color
            for item in self._squares
        )

    def is_legal(self, uci: str) -> bool:
        """Return whether text names a canonical legal move for this turn."""
        try:
            move = Move.from_uci(uci)
        except ValueError:
            return False
        return move in set(self._legal_move_objects({}))

    def legal_moves(self) -> tuple[str, ...]:
        """Return every legal move in unique bytewise ASCII order."""
        return tuple(sorted(move.uci() for move in self._legal_move_objects({})))

    def _legal_move_objects(
        self, memo: dict[str, tuple[Move, ...]]
    ) -> tuple[Move, ...]:
        key = self.position_key()
        cached = memo.get(key)
        if cached is not None:
            return cached

        mover = self.turn
        legal: list[Move] = []
        for move in self._pseudo_moves(mover):
            child = self.copy(include_history=False)
            child._apply_unchecked(move)
            if child.is_in_check(mover):
                continue
            legal.append(move)

        result = tuple(legal)
        memo[key] = result
        return result

    def _pseudo_moves(self, color: str) -> Iterator[Move]:
        for source, piece in enumerate(self._squares):
            if piece is None or piece_color(piece) != color:
                continue
            yield from self._piece_pseudo_moves(source, piece)
        yield from self._drop_pseudo_moves(color)

    def _piece_pseudo_moves(self, source: int, piece: str) -> Iterator[Move]:
        color = piece_color(piece)
        kind = base_type(piece)
        promoted = is_promoted(piece)
        source_file, source_rank = _coordinates(source)

        destinations: list[int] = []

        def step(delta_file: int, delta_rank: int) -> None:
            file_number = source_file + delta_file
            rank = source_rank + delta_rank
            if not _on_board(file_number, rank):
                return
            target = _index(file_number, rank)
            occupant = self._squares[target]
            if occupant is None or piece_color(occupant) != color:
                destinations.append(target)

        def slide(delta_file: int, delta_rank: int) -> None:
            file_number = source_file + delta_file
            rank = source_rank + delta_rank
            while _on_board(file_number, rank):
                target = _index(file_number, rank)
                occupant = self._squares[target]
                if occupant is None:
                    destinations.append(target)
                else:
                    if piece_color(occupant) != color:
                        destinations.append(target)
                    break
                file_number += delta_file
                rank += delta_rank

        forward = _forward(color)
        gold_steps = (
            (-1, forward),
            (0, forward),
            (1, forward),
            (-1, 0),
            (1, 0),
            (0, -forward),
        )

        if kind == "K":
            for delta_file in (-1, 0, 1):
                for delta_rank in (-1, 0, 1):
                    if delta_file or delta_rank:
                        step(delta_file, delta_rank)
        elif kind == "P" and promoted:
            for delta in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                slide(*delta)
        elif kind == "S" and promoted:
            for delta in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                slide(*delta)
        elif promoted and kind in {"N", "L"}:
            for delta in gold_steps:
                step(*delta)
        elif kind == "S":
            for delta in (
                (-1, forward),
                (0, forward),
                (1, forward),
                (-1, -forward),
                (1, -forward),
            ):
                step(*delta)
        elif kind == "N":
            step(-1, 2 * forward)
            step(1, 2 * forward)
        elif kind == "L":
            slide(0, forward)
        elif kind == "P":
            step(0, forward)
        else:
            raise AssertionError(f"unhandled Kyoto Shogi piece type: {kind}")

        for target in destinations:
            occupant = self._squares[target]
            if occupant is not None and base_type(occupant) == "K":
                # The arena stops at no legal moves; king capture is never a
                # public transcript move.
                continue
            if kind == "K":
                yield Move(source, target)
            elif promoted:
                yield Move(source, target, demote=True)
            else:
                yield Move(source, target, promote=True)

    def _drop_pseudo_moves(self, color: str) -> Iterator[Move]:
        for kind in HAND_ORDER:
            if self.hands[color][kind] <= 0:
                continue
            for target, occupant in enumerate(self._squares):
                if occupant is not None:
                    continue
                yield Move(None, target, drop_piece=kind)
                yield Move(None, target, drop_piece=f"+{kind}")

    def _has_unpromoted_pawn(self, color: str, file_number: int) -> bool:
        pawn = "P" if color == BLACK else "p"
        return any(
            self._squares[_index(file_number, rank)] == pawn
            for rank in range(BOARD_RANKS)
        )

    def _king_index(self, color: str) -> int:
        king = "K" if color == BLACK else "k"
        try:
            return self._squares.index(king)
        except ValueError as error:
            raise ValueError(f"position has no {color} king") from error

    def is_in_check(self, color: str | None = None) -> bool:
        """Return whether a king is geometrically attacked in this position."""
        checked = self.turn if color is None else color
        if checked not in COLORS:
            raise ValueError(f"unknown Kyoto Shogi color: {checked!r}")
        king = self._king_index(checked)
        attacker = opposite(checked)
        return any(
            piece is not None
            and piece_color(piece) == attacker
            and self._attacks(source, king, piece)
            for source, piece in enumerate(self._squares)
        )

    def is_square_attacked(self, square: str, by_color: str) -> bool:
        """Return whether a square is attacked, including by pinned pieces."""
        if by_color not in COLORS:
            raise ValueError(f"unknown Kyoto Shogi color: {by_color!r}")
        target = square_index(square)
        return any(
            piece is not None
            and piece_color(piece) == by_color
            and self._attacks(source, target, piece)
            for source, piece in enumerate(self._squares)
        )

    def _attacks(self, source: int, target: int, piece: str) -> bool:
        color = piece_color(piece)
        kind = base_type(piece)
        promoted = is_promoted(piece)
        source_file, source_rank = _coordinates(source)
        target_file, target_rank = _coordinates(target)
        delta_file = target_file - source_file
        delta_rank = target_rank - source_rank
        forward = _forward(color)

        if source == target:
            return False
        if kind == "K":
            return max(abs(delta_file), abs(delta_rank)) == 1
        if kind == "P" and promoted:
            return (delta_file == 0 or delta_rank == 0) and self._path_clear(
                source, target
            )
        if kind == "S" and promoted:
            return abs(delta_file) == abs(delta_rank) and self._path_clear(
                source, target
            )
        if promoted and kind in {"N", "L"}:
            return (delta_file, delta_rank) in {
                (-1, forward),
                (0, forward),
                (1, forward),
                (-1, 0),
                (1, 0),
                (0, -forward),
            }
        if kind == "S":
            return (delta_file, delta_rank) in {
                (-1, forward),
                (0, forward),
                (1, forward),
                (-1, -forward),
                (1, -forward),
            }
        if kind == "N":
            return (abs(delta_file), delta_rank) == (1, 2 * forward)
        if kind == "L":
            return (
                delta_file == 0
                and delta_rank * forward > 0
                and self._path_clear(source, target)
            )
        if kind == "P":
            return delta_file == 0 and delta_rank == forward
        raise AssertionError(f"unhandled Kyoto Shogi attack type: {kind}")

    def _path_clear(self, source: int, target: int) -> bool:
        source_file, source_rank = _coordinates(source)
        target_file, target_rank = _coordinates(target)
        delta_file = (target_file > source_file) - (target_file < source_file)
        delta_rank = (target_rank > source_rank) - (target_rank < source_rank)
        if not (
            source_file == target_file
            or source_rank == target_rank
            or abs(target_file - source_file) == abs(target_rank - source_rank)
        ):
            return False
        file_number = source_file + delta_file
        rank = source_rank + delta_rank
        while (file_number, rank) != (target_file, target_rank):
            if self._squares[_index(file_number, rank)] is not None:
                return False
            file_number += delta_file
            rank += delta_rank
        return True

    def _apply_unchecked(self, move: Move) -> tuple[str, str | None]:
        mover = self.turn
        captured: str | None = None
        if move.is_drop:
            face = move.drop_piece
            if face is None or face.lstrip("+") not in HAND_ORDER:
                raise AssertionError("unchecked drop has invalid piece")
            kind = face.lstrip("+")
            self.hands[mover][kind] -= 1
            base = kind if mover == BLACK else kind.lower()
            piece = f"+{base}" if face.startswith("+") else base
            self._squares[move.target] = piece
        else:
            if move.source is None:
                raise AssertionError("unchecked board move has no source")
            piece = self._squares[move.source]
            if piece is None:
                raise AssertionError("unchecked board move has no piece")
            captured = self._squares[move.target]
            self._squares[move.source] = None
            if captured is not None:
                self.hands[mover][base_type(captured)] += 1
            if move.promote:
                piece = f"+{piece}"
            elif move.demote:
                piece = piece[-1]
            self._squares[move.target] = piece
        if captured is None:
            self.no_capture_plies += 1
        else:
            self.no_capture_plies = 0
        if mover == WHITE:
            self.fullmove_number += 1
        self.turn = opposite(mover)
        self.played_ply_count += 1
        return piece, captured

    def push(self, uci: str) -> AppliedMove:
        """Apply one legal UCI move and extend independent adjudication history."""
        if self.outcome().finished:
            raise ValueError("cannot move after the Kyoto Shogi game has ended")
        move = Move.from_uci(uci)
        legal = set(self._legal_move_objects({}))
        if move not in legal:
            raise ValueError(f"illegal Kyoto Shogi move: {uci}")

        mover = self.turn
        piece, captured = self._apply_unchecked(move)
        key = self.position_key()
        self._position_counts[key] += 1
        applied = AppliedMove(
            uci=move.uci(),
            color=mover,
            piece=piece,
            captured=captured,
            is_drop=move.is_drop,
            promoted=move.promote,
            gave_check=self.is_in_check(),
            fen_after=self.fen(),
            position_key_after=key,
            played_ply_count=self.played_ply_count,
            position_occurrences=self._position_counts[key],
        )
        self._move_history.append(applied)
        self._state_keys.append(key)
        return applied

    def is_checkmate(self) -> bool:
        """Return whether the checked side to move has no legal board move."""
        return self.is_in_check() and not self._legal_move_objects({})

    def is_stalemate(self) -> bool:
        """Return whether the safe side to move has no legal board move."""
        return not self.is_in_check() and not self._legal_move_objects({})

    def resign(self) -> Outcome:
        """Record an immediate loss for the resigning side without moving."""
        if self.outcome().finished:
            raise ValueError("cannot resign after the Kyoto Shogi game has ended")
        winner = opposite(self.turn)
        self._forced_outcome = Outcome(f"{winner}_win", winner, "resignation")
        return self._forced_outcome

    def _repetition_outcome(self) -> Outcome | None:
        key = self.position_key()
        occurrences = [
            index for index, state_key in enumerate(self._state_keys) if state_key == key
        ]
        if len(occurrences) < FOURFOLD_OCCURRENCES:
            return None
        first = occurrences[0]
        fourth = occurrences[3]
        interval = self._move_history[first:fourth]
        continuous: list[str] = []
        for color in (BLACK, WHITE):
            color_moves = [move for move in interval if move.color == color]
            if color_moves and all(move.gave_check for move in color_moves):
                continuous.append(color)
        if len(continuous) == 1:
            loser = continuous[0]
            winner = opposite(loser)
            return Outcome(f"{winner}_win", winner, "rule_claim")
        return Outcome("draw", None, "rule_claim")

    def outcome(self) -> Outcome:
        """Adjudicate no-move loss and the pinned fourfold rule."""
        if self._forced_outcome is not None:
            return self._forced_outcome
        legal = self._legal_move_objects({})
        if not legal:
            winner = opposite(self.turn)
            termination = "checkmate" if self.is_in_check() else "stalemate"
            return Outcome(f"{winner}_win", winner, termination)
        repetition = self._repetition_outcome()
        if repetition is not None:
            return repetition
        return Outcome("ongoing", None, None)


def replay(fen: str, moves: Iterable[str]) -> tuple[Board, tuple[AppliedMove, ...]]:
    """Replay canonical UCI moves and return the board plus derived step facts."""
    board = Board(fen)
    applied = tuple(board.push(move) for move in moves)
    return board, applied


def fen_from_pieces(
    pieces: Mapping[str, str],
    *,
    turn: str = BLACK,
    hands: Mapping[str, Mapping[str, int]] | None = None,
    no_capture_plies: int = 0,
    fullmove_number: int = 1,
) -> str:
    """Build a canonical synthetic FEN fixture from square and hand mappings."""
    if turn not in COLORS:
        raise ValueError(f"unknown Kyoto Shogi color: {turn!r}")
    if fullmove_number < 1:
        raise ValueError("fixture move number must be positive")
    squares: list[str | None] = [None] * BOARD_SIZE
    for square, piece in pieces.items():
        if not _valid_piece_token(piece):
            raise ValueError(f"unknown Kyoto Shogi fixture piece: {piece!r}")
        index = square_index(square)
        if squares[index] is not None:
            raise ValueError(f"duplicate Kyoto Shogi fixture square: {square}")
        squares[index] = piece

    rows: list[str] = []
    for rank in range(BOARD_RANKS):
        parts: list[str] = []
        empty = 0
        for column in range(BOARD_FILES):
            piece = squares[rank * BOARD_FILES + column]
            if piece is None:
                empty += 1
            else:
                if empty:
                    parts.append(str(empty))
                    empty = 0
                parts.append(piece)
        if empty:
            parts.append(str(empty))
        rows.append("".join(parts))

    hand_tokens: list[str] = []
    hand_mapping = hands or {}
    for color in (BLACK, WHITE):
        counts = hand_mapping.get(color, {})
        for kind in HAND_ORDER:
            count = counts.get(kind, 0)
            if count < 0:
                raise ValueError("fixture hand count cannot be negative")
            token = kind if color == BLACK else kind.lower()
            hand_tokens.extend(token for _ in range(count))
    hand_field = "".join(hand_tokens)
    active = "w" if turn == BLACK else "b"
    return (
        f"{'/'.join(rows)}[{hand_field}] {active} - - "
        f"{no_capture_plies} {fullmove_number}"
    )
