Play the pinned board game of Kyoto Shogi as White through `/app/arena` and win
specifically by checkmate. The task is to choose moves and drops in the active
match; no software build or package modification is required. A
stalemate/no-move win, rule-claim result, draw, resignation, loss, or unfinished
game is not a successful outcome.

Kyoto Shogi is a 5-by-5 drop game whose pawn/rook, silver/bishop,
knight/gold, and lance/gold pieces must flip faces after every board move.
Captured identities return as holdings and may be dropped with either face.
`/app/README.md` is the binding external specification for the complete rules,
terminal conditions, exact move and drop tokens, arena commands, error results,
and public JSON contract. The game has no reset, rewind, position loader, or
analysis command.

An accepted ongoing White action atomically includes Black's reply in its
completed response. If the position becomes unrecoverable, use
`/app/arena resign` instead of allowing the session to expire. A reported win,
loss, draw, or resignation is terminal: issue no further arena commands and end
your turn immediately.
