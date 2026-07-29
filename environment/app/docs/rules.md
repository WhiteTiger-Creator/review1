Garnet Board Watch plays out a board of discs. It is handed a board at a time, and for each one it
reports whether the player who is about to move can force a win, and when they can, one shove
that does it. Each board stands on its own; nothing carries from one board to the next. When
more than one shove wins a board any one of them may be the one named.

The board. A board is a one-way road that ends at a ledge. A line of discs stands on it, front
to back, the front disc nearest the ledge. Each disc has a room, the empty road in front of
it: the front disc's room is the space between it and the ledge, and every other disc's
room is the space between it and the disc ahead of it. A room is a whole number of
spaces, nought or more. A room of nought means the disc is snug, its bumper already
against the ledge or against the disc ahead. The discs are numbered from one at the front, and
an empty room is counted in that numbering like any other.

The move. The two players take turns. On a turn the player to move picks a single disc and
shoves it forward, toward the ledge. The shove moves the disc ahead by at least one space and at
most up to the point where its bumper meets the disc ahead of it, or the ledge if it is the
front disc. When the road sets a nudge, one shove may carry a disc no further than that many
spaces, so a disc advances by at least one space and at most the smaller of its room and
the nudge, and a disc standing further off its leader than the nudge cannot be brought all the
way up to it on a single turn. Shoving a disc forward closes its own room by the distance shoved and opens the
room of the disc behind it by that same distance, since the disc behind now has more road
in front of it; the disc that was shoved is the one that moves and no other disc moves. Shoving
the back disc forward, which has no disc behind it, opens nothing behind. A disc whose room
is nought cannot be shoved, having no room in front of it, until the disc ahead of it moves
away and gives it room.

Scoring. Shove the front disc forward its whole room and it comes to rest against the
ledge. There it scores and is lifted off the board, and the disc that stood behind it becomes the
new front disc, with the ledge now in front of it. The line is one disc shorter, and the disc
newly at the front measures its room to the ledge. Shoving the front disc less than its
whole room leaves it on the board, nearer the ledge than before. Only the front disc can
reach the ledge, and only by a shove that spends its whole room. Where the road sets a
nudge, a single shove spends the whole room only when the room is no greater than the
nudge, so a front disc standing further off the ledge than the nudge cannot score on this turn and
must be crawled toward the ledge a nudge at a time over several turns before it can be lifted off.

Who wins. The players shove in turn, and whoever makes the last shove wins, the shove after
which no disc on the board can move at all. A player faced with a board where every disc is snug,
so no disc has room in front of it, cannot move and has lost, for the other player made the
last shove on the turn before. A board with no discs left on it, every disc scored, is a loss for
the player to move for the same reason. So long as some disc has room in front of it and the
road allows a shove of at least one space, the player to move has a shove to make; only where the
nudge is nought, which forbids every shove, does a board with room to spare still leave the player
to move unable to stir a disc, and that too is a loss. There is always a definite answer under best play: for the player
to move, either every shove hands the win to the other player, and the board is a loss, or some
shove forces the win, and the board is a win. The tool reports which, and for a win it names one
shove that forces it.

The shove named. When the player to move loses, the output says so and names no shove. When
the player to move wins, the output names one shove that leaves the other player a lost board,
a board from which they in turn cannot force a win. Any legal shove that reaches such a board is
accepted. A shove must move one disc forward by at least one space and at most the smaller of its
room and the nudge where the road sets one, and a shove of the front disc by its whole
room scores it as above. A shove is written

    shove disc I forward D

where I is the disc number, counted from one at the front, and D is the number of spaces the
disc is shoved forward. When I is the front disc and D is its whole room, that shove scores
the front disc; it is written the same way.

Invocation and input and output. The path to the board file is the single command-line
argument. If the program is run with anything other than exactly one argument, or the file
cannot be read, it writes nothing and exits with status 2. Otherwise boards arrive on standard
input, one per line, in order, and the program exits 0. A board line is split on whitespace
into fields. A field is a whole-number literal when it is an optional single leading plus or
minus sign followed by one or more decimal digits, and nothing else, and the number it spells
fits a signed 64-bit integer. A run of digits too large to fit one is not a whole-number
literal. A line with no fields, or any field that is not a whole-number literal, is skipped
and produces no output. Every other line produces exactly one output line, in input order.

Reading a board. Each field of a board line is the room of one disc, in order from the
front, and is read as the whole number the literal spells. A negative field like -1 is a whole
number all the same: it is read as that number and then judged out of range, never treated as
a non-number and never skipped on that account. A room is in range when it is nought or
more and, when the board file sets a span, no greater than that span. When every field is a
whole-number literal but at least one room is out of range, whether below nought or above
the span, the board is not a legal setup for this road: the output echoes it and reports the
word VOID, with no call and no shove. The span bounds only the rooms of a board as it
is read from input; it does not bound the rooms that open up as discs shove and score during
play, which may carry a disc past it. The nudge never bounds a room at all: a disc may stand
any number of spaces off its leader that the span allows, and simply takes more turns to close
a wide gap when the road caps how far it shoves at once. A room of nought is a snug disc: it is part of the
board and holds its place in the numbering, but it has no room in front and cannot be shoved; a
front disc standing snug against the ledge is not lifted off on that account, but stays on the
board until a shove takes it to the ledge, which from a snug stand it cannot make. The board is echoed at the front of its output line as the disc rooms in that
order, each read from its literal and written back in plain decimal and joined by single
spaces, so a field written 007 echoes as 7 and a field written +3 echoes as 3.

The board file. The board file is read one line at a time. Everything from the first # on a
line to the end of the line is a comment and is dropped, and the surrounding whitespace is
then trimmed. A line that begins with span: sets the largest room a single disc may hold
at this road, read from the first word after span: when that word is a run of decimal digits
naming a whole number nought or more that fits a signed 64-bit integer; a word that is not
such a run, whether it carries a sign or is too large to fit, leaves the setting where it
stood. When a span is set more than once the last line that sets a value stands, and when it
is never set there is no span and every room of nought or more is in range. A line that
begins with nudge: sets the nudge for this road, the most spaces one disc may be shoved forward on
a single turn, read from the first word after nudge: under the very same rule as the span: a
run of decimal digits naming a whole number nought or more that fits a signed 64-bit integer
sets it, and any other word, whether it carries a sign or is too large to fit, leaves the nudge
where it stood. The last nudge: line that sets a value stands, and a road that never sets a nudge
puts no cap on a shove, so a disc may be shoved its whole room at once. The span and the
nudge are set apart, each read from its own line, and either may be given without the other. All
other lines of the board file are ignored.

Output and exit codes. Each board that produces output prints a single line

    ROOMS | CALL

where ROOMS is the disc rooms in order, each in decimal, joined by single spaces, and
CALL is one of three things. It is the word VOID when a room is out of range for
this road. Otherwise it is the word STUCK when the player to move cannot force a win, standing
alone with no shove after it, including on the all-snug board and the empty board. Otherwise it
is the word FORCED when the player to move can force a win, followed by a single space and the
chosen shove. The program exits 0 once every input line has been read.
