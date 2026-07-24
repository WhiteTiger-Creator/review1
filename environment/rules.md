# Dropforge: the rules card

Dropforge is a terminal falling-block game played in a well 9 columns wide
and 16 rows deep.
This card states the universal core.
The arcade ran its own conventions on top, and the recorded games are the
only record of them.

## Pieces

Five piece shapes exist, named I, O, L, S, T.
Each script entry gives the piece name, a rotation index, and a target
column for the shape's left edge:

    {"piece": "L", "rot": 2, "col": 5}

Rotation indexes select from the shape's rotation list (the O piece has
one rotation, the I and S pieces two, the L and T pieces four); an index
past the list wraps around.
Shape cells for every rotation are drawn in the recorded games' final
wells; piece ids in a well are the 1-based script positions of the pieces
whose cells they are.

## Play

Pieces drop one at a time; there is no timer and no steering after the
drop.
A piece falls straight down until some cell of it would pass the floor or
rest on a filled cell.
Completed rows clear and the material above a clear falls.
Clearing rows scores points, and the score line of each recording shows
the running total the house paid by the end of that game.
The well walls are solid: a piece cannot extend past them.

## Recordings

A recorded game holds the script and the true final state: the well as a
16 by 9 grid of piece ids (0 for empty) and the final score.
Play is fully deterministic, so the same script always reproduces the same
final well and score.
