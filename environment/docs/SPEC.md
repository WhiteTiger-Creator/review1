# Path-tile flow settlement — authoritative rules

This file is the whole rulebook for one move of a path-tile board game on a
square grid. Every rule here is graded. The public examples at the end
illustrate the rules; they are never the whole of the contract. Any
plausible alternative house rule that disagrees with a clause here settles a
different position and scores zero.

Each instance hands you the current board of placed path tiles, a set of tokens
standing on edge-points, and the move: the active token's tile is placed on the
empty cell that token faces. You settle the flow that follows and return, for
every token, either where it comes to rest or that it left play.

## Board and coordinates

- The board is a square grid of side n. A cell is a pair of integers
  [col, row] with 0 <= col < n and 0 <= row < n. col grows to the east (right),
  row grows to the north (up).
- A cell is either empty or holds one path tile.
- The four sides of a cell are north (toward row plus one), east (toward col
  plus one), south (toward row minus one), and west (toward col minus one).
- Two cells are adjacent when they differ by one in exactly one coordinate. The
  cell to the north of [c, r] is [c, r plus 1], to the east is [c plus 1, r], to
  the south is [c, r minus 1], to the west is [c minus 1, r].

## Edge-points

Every side of a cell carries two edge-points, so a cell has eight edge-points in
all. They are numbered 0 through 7 going clockwise, starting at the left point
of the north side:

- 0 north side, west point
- 1 north side, east point
- 2 east side, north point
- 3 east side, south point
- 4 south side, east point
- 5 south side, west point
- 6 west side, south point
- 7 west side, north point

Two adjacent cells share one side and therefore share the two edge-points on
that side. The identifications on each shared side are:

- north-of / south-of: point 0 of a cell is point 5 of its north neighbour, and
  point 1 is point 4 of that neighbour.
- east-of / west-of: point 2 of a cell is point 7 of its east neighbour, and
  point 3 is point 6 of that neighbour.

A token standing on an edge-point of a cell and facing into that cell is,
equivalently, standing on the identified edge-point of the neighbour on the
other side. Two tokens may never occupy the same edge-point at the start.

## Path tiles and rotations

A path tile carries four painted paths. Each path joins two of the eight
edge-points, and the four paths together use all eight points, each exactly
once, so a tile is four disjoint pairs of edge-points. The paths do not cross.

A tile may be laid in any of its rotations. Rotating a tile ninety degrees
clockwise sends the edge-point numbered k to the edge-point numbered (k plus 2)
taken modulo 8. A placed tile is given by its four painted-path pairs already in
the rotation it was laid, so the pairs listed for a placed tile are the actual
connections on the board.

When a token enters a tile at one edge-point, the painted path carries it to the
partner edge-point paired with that point on the tile.

## Following the paths

Only tokens facing the cell where the new tile is placed take part in the flow.
Every such token advances at the same time; all other tokens stay exactly where
they are.

An advancing token follows this walk across the fixed layout of tiles:

1. The token faces a cell at some entry edge-point.
2. If that cell is off the board, the token has left the board and is out.
3. If that cell is empty, the token stops there and comes to rest facing that
   cell at the entry edge-point.
4. Otherwise the cell holds a tile. The token enters at its edge-point, follows
   the painted path to the partner edge-point, and crosses that side into the
   next cell, arriving at the identified edge-point of that next cell. Return to
   step 1.

The edge-point a token arrives at after crossing is fixed by the identifications
above: leaving a tile at point 0 or 1 crosses north and arrives at point 5 or 4;
at point 2 or 3 crosses east and arrives at point 7 or 6; at point 4 or 5
crosses south and arrives at point 1 or 0; at point 6 or 7 crosses west and
arrives at point 3 or 2.

The layouts supplied always let every advancing token reach a resting cell or
the rim after finitely many tiles.

## Leaving the board and collisions

A token that crosses a side on the rim of the board, into a cell that is off the
grid, has left the board and is eliminated.

The tokens advance at the same time, so two tokens that meet collide. Record,
for each advancing token, the full trace of edge-points it occupies: its entry
point, every point it crosses through, and its resting point if it stops. A
token that stays keeps only its single current edge-point. An edge-point is
contested when it lies in the trace of two or more distinct tokens. Every token
whose trace contains a contested edge-point is eliminated by collision, whether
the meeting is at a resting point or midway along the flow.

A token is eliminated exactly when it leaves the board or when it shares a
contested edge-point with another token. Every other token survives. A surviving
advancing token rests at the empty cell and entry edge-point where its walk
stopped; a surviving token that stayed keeps its original cell and edge-point.

## Input

One instance per input line, one small object per line, holding these fields:

- n, the side of the board.
- board, the list of placed tiles, each written as an object with sq set to
  [col, row] and paths set to the four painted-path pairs of that tile.
- tokens, the list of tokens, each written as an object with cell set to the
  [col, row] cell the token faces and p set to its entry edge-point, an integer
  0 through 7. The faced cell is empty and on the board. No two tokens share an
  edge-point.
- active, the index into tokens of the token whose move this is.
- tile, the four painted-path pairs of the tile the active token lays on the
  cell it faces.

The board given is always legal and every instance is playable.

## Output

One line per input line, in input order, in exactly this shape:

```
TOKENS <k><entries>
```

- <k> is the number of tokens, equal to the length of the input token list.
- <entries> lists one space then a token entry for each token, in the same order
  as the input tokens, indexed from 0.
- A surviving token i is written i:col.row.point, giving the cell and entry
  edge-point where it rests.
- An eliminated token i is written i:out.

If any field is inconsistent or the flow cannot settle, the whole line is
exactly ILLEGAL. Supplied instances never trigger this.

## Public examples

A lone token faces the middle cell of a four-wide board at edge-point 7; the
laid tile joins 7 and 2, so the token runs straight east one tile and rests
facing the next cell:

```
{"n":4,"board":[],"tokens":[{"cell":[1,1],"p":7}],"active":0,"tile":[[7,2],[6,3],[0,5],[1,4]]}
-> TOKENS 1 0:2.1.7
```

A token faces a rim cell at edge-point 7; the laid tile joins 7 and 6, both on
the west side, so the token turns straight back out through the west rim and
leaves the board:

```
{"n":3,"board":[],"tokens":[{"cell":[0,1],"p":7}],"active":0,"tile":[[6,7],[0,5],[1,4],[2,3]]}
-> TOKENS 1 0:out
```

Two tokens face the same cell at edge-points 7 and 2; the laid tile joins 7 and
2, so the two run head-on along the one painted path, meet, and both are
eliminated by collision:

```
{"n":4,"board":[],"tokens":[{"cell":[1,1],"p":7},{"cell":[1,1],"p":2}],"active":0,"tile":[[7,2],[6,3],[0,5],[1,4]]}
-> TOKENS 2 0:out 1:out
```

A token faces a cell with two straight tiles already lying east of it; the laid
tile is straight too, so the token runs east across three tiles in a row before
resting:

```
{"n":5,"board":[{"sq":[2,2],"paths":[[7,2],[6,3],[0,5],[1,4]]},{"sq":[3,2],"paths":[[7,2],[6,3],[0,5],[1,4]]}],"tokens":[{"cell":[1,2],"p":7}],"active":0,"tile":[[7,2],[6,3],[0,5],[1,4]]}
-> TOKENS 1 0:4.2.7
```
