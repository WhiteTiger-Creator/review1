# Kyoto Shogi arena

You play White (the uppercase, first-moving side) in one immutable 5-by-5
game of Kyoto Shogi against Black. The only interface is `/app/arena`; there
is no reset, undo, position loader, analysis command, seed, model selector, or
difficulty control.

## Commands and stopping

Run exactly one arena command at a time and wait for its complete response:

```text
/app/arena status
/app/arena move MOVE
/app/arena resign
/app/arena transcript
```

Place `--json` or `--wire` immediately after `/app/arena` for that format. A
White move and Black reply are one atomic turn. Never batch or pre-queue a
second command. After a response reports a result other than `ongoing`, send
no more arena requests and end your turn immediately.

## Board and opening

Files are `a` through `e`; ranks are `1` through `5`. Uppercase pieces are
White, lowercase pieces are Black, and White moves toward increasing ranks.
The public board displays each piece's current movement face:

```text
5  p g k s g
4  . . . . .
3  . . . . .
2  . . . . .
1  G S K G P
   a b c d e
```

The pinned start profile is `p+nks+l/5/5/5/+LSK+NP[-] w 0 1`; the `+n`,
`+l`, `+N`, and `+L` tokens explain the displayed gold faces. Public live
positions use six-field FEN; before play it is
`p+nks+l/5/5/5/+LSK+NP[] w - - 0 1`. Brackets contain captured identities
available for drops. The last fields are captureless plies and fullmoves.

## Two-sided pieces and mandatory flipping

Every non-king piece has two faces. A board move must flip it to the other
face; there is no promotion zone and no option to keep the same face.

- `P` pawn steps one square forward; `+P` is a rook sliding orthogonally.
- `S` silver steps forward, forward-diagonally, or backward-diagonally; `+S`
  is a bishop sliding diagonally.
- `N` knight jumps two forward and one sideways; `+N` moves as a gold.
- `L` lance slides straight forward; `+L` moves as a gold.
- `K` king steps one square in any direction and never flips.
- A gold face steps forward, forward-diagonally, sideways, or straight back.

An unpromoted-face board move therefore ends in `+`, such as `b1c2+`. A
promoted-face move ends in `-`, such as `a1a2-`. King moves have no suffix.
A move may not leave its own king attacked.

## Captures and alternative-face drops

A capture removes the enemy piece and adds its base identity (`P`, `S`, `N`,
or `L`) to the capturer's holdings. A held identity may be dropped on any
empty square with either face: `P@c3` drops its pawn face and `+P@c3` drops
its rook face. Kyoto Shogi has no nifu, uchifuzume, last-rank immobility, or
drop-zone restriction. A drop does not flip immediately; it flips after its
next board move. Submit exactly one token from the current sorted
`legal_moves` list.

## Results

Checkmate wins. Having no legal move while not checked is also a loss, labeled
`stalemate`. The fourth occurrence of a position is a draw unless one side
gave continuous check, in which case that checking side loses. The public
termination label is `rule_claim`. Resignation produces `black_win` with
termination `resignation` and never earns credit.

While live, `result` is `ongoing` and `winner` and `termination` are null.
Terminal results are `white_win`, `black_win`, or `draw`.

## JSON contract

`/app/arena --json status` and successful `move` or `resign` return:

```text
ok, protocol, variant, player_color, start_fen, fen, position_hash, board,
turn, result, winner, termination, ply_count, postgame_player_requests,
last_move, legal_moves, holdings
```

`protocol` is `arena-kyoto-shogi-v1`, `variant` is `kyotoshogi`, and
`player_color` is `white`. Each `holdings` object has `color`, `piece`, and
`count`. `legal_moves` is sorted and unique, and is empty after terminal play.

`last_move` has `ply`, `actor`, `color`, `uci`, `san`, `fen_after`, and
`hash_after`. `san` is informational; submit `uci`. `actor` alternates
`player`, `opponent`; `color` alternates `white`, `black`.

A rejected request returns `ok:false`, then `error`, then unchanged `state`.
The `error` object has `code` and `message`. Codes are `bad_request`,
`illegal_move`, `wrong_turn`, `game_over`, `opponent_error`, and
`unknown_command`. `/app/arena --json transcript` returns `ok`, `state`,
`protocol`, `variant`, `start_fen`, and the complete append-only `moves`.

## Wire contract

Wire output begins with `FAIRY_ARENA_WIRE_V1`, ends with `END`, and uses:

```text
SETTINGS  protocol  variant  player_color  start_fen
STATE     turn result winner termination ply postgame_requests fen hash
BOARD     five slash-separated expanded board rows
LEGAL     move
HOLDING   color piece count
ACTION    ply actor color uci san fen_after hash_after
END
```

A failure inserts `ERROR code message` after the header and supplies unchanged
state. `position_hash` and every `hash_after` are sixteen lowercase hexadecimal
digits. Accepted actions are append-only; syntax, legality, opponent failure,
and protected-state failures are atomic. `postgame_player_requests` counts
participant connections after game end and must remain zero for successful
play.
