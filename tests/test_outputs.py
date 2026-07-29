"""Verification suite for Garnet Board Watch.

The game is a line of discs on a one-way board that ends at a ledge. A turn shoves one disc forward
by at least one space and at most up to the bumper of the disc ahead, or the ledge for the front
disc; shoving a disc forward opens by that same distance the room of the disc behind it, and
the front disc shoved its whole room scores at the ledge and is lifted off, dropping the line
by one disc. Whoever makes the last shove wins. Each board stands on its own.

The road may set a nudge: the most spaces one disc may be shoved forward on a single turn. Under a
nudge a shove is capped at the smaller of the room and the nudge, so a wide gap is closed a
nudge at a time, and the front disc scores only when its room is no greater than the nudge.

Every board has a definite answer under best play, and it is cross-checked here two ways: a full
game search that knows nothing of any shortcut plays each small board out to the end, and a
closed reckoning over the rooms is required to agree with that search on every small board,
with and without a nudge. The reckoning is then run against the tool: its call on each board
must match, and every winning shove it names is replayed and required to leave the other player a
lost board. Hand cases pin the echo and the numbering, the snug discs, the out-of-range boards,
the skipping of junk lines, the board-file reading and the exit codes. The boards whose front disc
stands at the ledge, the boards with an even count of discs, and the capped boards are pinned on
their own, since a reading fixed from the ledge, or one that ignores the nudge, calls them wrong.

The engine is always started through an unprivileged runner, and the verifier's own files are
locked to root, so the engine cannot read this reference and echo its answers back: it has to
settle the boards itself.
"""

import functools
import itertools
import os
import pathlib
import random
import re
import shutil
import subprocess
import tempfile

BIN = "/tmp/shovehalf"
SHOVE_TERM = re.compile(r"^shove disc (\d+) forward (\d+)$")

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1

# The engine is always started through this runner, which drops to an unprivileged
# user first. The verifier's own files are root-only (test.sh locks them down), so the
# engine cannot read the reference below and echo its answers back: it has to settle
# the boards itself. HOME is pointed at a world-writable directory so the runtime has
# somewhere to fall back on while it runs as the unprivileged user.
SANDBOX = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", "--"]
_ENV = dict(os.environ, HOME="/tmp")


def sandboxed(argv, stdin_text, timeout=120.0):
    """Run argv as the unprivileged user and return the completed process."""
    return subprocess.run(SANDBOX + argv, input=stdin_text, capture_output=True,
                          text=True, timeout=timeout, env=_ENV, check=False)


def run_bin(span, positions, nudge=None, timeout=120.0):
    """Feed a batch of boards at a road with the given room span (None for no span) and
    the given shove nudge (None for no cap) and return the output lines."""
    text = ""
    if span is not None:
        text += f"span: {span}\n"
    if nudge is not None:
        text += f"nudge: {nudge}\n"
    return _run(text, positions, timeout)


def run_bin_text(text, positions, timeout=120.0):
    """Run with a raw board-file body (for the file-parsing tests)."""
    return _run(text, positions, timeout)


def _run(text, positions, timeout):
    """Write the board-file body to a private temp dir, feed the position lines on standard
    input and return the output lines, asserting the run exited clean."""
    root = tempfile.mkdtemp(prefix="garnet-board-watch-")
    try:
        os.chmod(root, 0o755)
        path = os.path.join(root, "board.txt")
        pathlib.Path(path).write_text(text, encoding="utf-8")
        os.chmod(path, 0o644)
        inp = "\n".join(positions) + "\n"
        p = sandboxed([BIN, path], inp, timeout=timeout)
        assert p.returncode == 0, f"garnet-board-watch exited {p.returncode}: {p.stderr[:500]}"
        return p.stdout.split("\n")[:-1] if p.stdout else []
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ----- closed reckoning ------------------------------------------------------


def live(idx, n):
    """Whether the disc at 0-based position idx in a line of n discs bears on best play: the
    alternation is counted from the back disc, whose parity is n-1."""
    return idx % 2 == (n - 1) % 2


def bearing(g, nudge):
    """The amount of a room that bears on best play. With no nudge the whole room
    bears; with a nudge, a disc crawls at most that far a turn, so only the residue of the
    room against a full stride of nudge-plus-one bears."""
    if nudge is None:
        return g
    return g % (nudge + 1)


def weigh(gaps, nudge=None):
    """Fold the bearing rooms of the live discs into one number; a board is a loss for the
    player to move exactly when this is nought."""
    n = len(gaps)
    x = 0
    for i in range(n):
        if live(i, n):
            x ^= bearing(gaps[i], nudge)
    return x


def call_of(gaps, nudge=None):
    """The call the reckoning gives a board: STUCK when the fold is nought, FORCED otherwise."""
    return "STUCK" if weigh(gaps, nudge) == 0 else "FORCED"


# ----- full game search over small boards -------------------------------------


def _moves(state, nudge):
    """Every board reachable by one legal shove. Shoving disc i forward by d closes its room
    by d and opens the room of the disc behind by d; shoving the back disc opens nothing;
    shoving the front disc its whole room scores it and drops the front disc from the line. A
    shove advances a disc by 1..room, and never by more than the nudge when the road sets one."""
    n = len(state)
    out = []
    for i in range(n):
        gi = state[i]
        hi = gi if nudge is None else min(gi, nudge)
        for d in range(1, hi + 1):
            if i == 0:
                if d == gi:
                    if n == 1:
                        out.append(())
                    else:
                        out.append((state[0] + state[1], *state[2:]))
                else:
                    ns = list(state)
                    ns[0] = gi - d
                    if n >= 2:
                        ns[1] += d
                    out.append(tuple(ns))
            elif i < n - 1:
                ns = list(state)
                ns[i] = gi - d
                ns[i + 1] += d
                out.append(tuple(ns))
            else:
                ns = list(state)
                ns[i] = gi - d
                out.append(tuple(ns))
    return out


@functools.cache
def _wb(state, nudge):
    """Whether the player to move on this board wins under best play, memoized over the search."""
    return any(not _wb(m, nudge) for m in _moves(state, nudge))


def win_search(gaps, nudge=None):
    """Play the board out to the end and say whether the player to move wins."""
    return _wb(tuple(gaps), nudge)


def search_call(gaps, nudge=None):
    """The call the played-out search gives a board, for cross-checking the reckoning."""
    return "FORCED" if win_search(gaps, nudge) else "STUCK"


# ----- parsing helpers -------------------------------------------------------


def is_int_literal(s):
    """Whether a field is a whole-number literal: an optional single leading sign and then
    one or more decimal digits."""
    if not s:
        return False
    if s[0] == "+" or s[0] == "-":
        s = s[1:]
    return len(s) > 0 and all("0" <= c <= "9" for c in s)


def parse_line(line):
    """Return the parsed rooms (a line that produces output), or None for a line that is
    skipped: no fields, a field that is not a whole-number literal, or a field too large to fit
    a signed 64-bit integer."""
    fields = line.split()
    if not fields:
        return None
    gaps = []
    for f in fields:
        if not is_int_literal(f):
            return None
        v = int(f)
        if v < INT64_MIN or v > INT64_MAX:
            return None
        gaps.append(v)
    return gaps


def in_range(gaps, span):
    """Whether every room is nought or more and, when the road sets a span, no wider than it."""
    return all(not (g < 0 or (span is not None and g > span)) for g in gaps)


def apply_shove(gaps, i, d):
    """Replay a shove of disc i (numbered from one at the front) forward by d spaces, scoring the
    front disc when d spends its whole room."""
    n = len(gaps)
    g = list(gaps)
    if i == 1 and d == g[0]:
        if n == 1:
            return []
        return [g[0] + g[1], *g[2:]]
    if i == 1:
        g[0] -= d
        if n >= 2:
            g[1] += d
        return g
    if i < n:
        g[i - 1] -= d
        g[i] += d
        return g
    g[i - 1] -= d
    return g


# ----- output validation -----------------------------------------------------


def check_output_line(line, gaps, span, nudge=None, truth=None):
    """Validate one output line against the reckoning. For a win, replay the reported shove and
    require it legal and winning: within the nudge, no farther than the room, and leaving the
    other player a board whose reckoning is nought."""
    assert " | " in line, ("no separator", line)
    echo, verd = line.split(" | ", 1)
    assert echo == " ".join(str(g) for g in gaps), ("echo", echo, gaps)

    if not in_range(gaps, span):
        assert verd == "VOID", ("out of range but not VOID", line, gaps, span)
        return

    want = call_of(gaps, nudge)
    if truth is not None:
        assert truth == want, ("reckoning disagrees with the search", gaps, nudge, want, truth)

    if verd == "STUCK":
        assert want == "STUCK", ("said STUCK, reckoning says FORCED", gaps, nudge)
        return
    assert verd.startswith("FORCED"), ("bad call", verd, line)
    assert want == "FORCED", ("said FORCED, reckoning says STUCK", gaps, nudge)
    body = verd[len("FORCED"):]
    assert body.startswith(" "), ("FORCED must be followed by a shove", verd)
    move = body[1:]

    m = SHOVE_TERM.match(move)
    assert m, ("bad shove", move, line)
    i = int(m.group(1))
    d = int(m.group(2))
    assert 1 <= i <= len(gaps), ("disc index out of range", i, line)
    assert d >= 1, ("shoved nothing", move)
    assert d <= gaps[i - 1], ("shoved past the disc ahead", move, gaps)
    if nudge is not None:
        assert d <= nudge, ("shoved farther than the nudge", move, nudge, gaps)
    after = apply_shove(gaps, i, d)
    assert weigh(after, nudge) == 0, ("shove does not leave a loss", gaps, nudge, move, after)


def check_batch(span, positions, nudge=None, brute=False):
    """Run a batch of boards and validate each output line on its own, since nothing carries
    from one board to the next. When brute is set, an in-range board is also cross-checked against
    a full game search."""
    got = run_bin(span, positions, nudge=nudge)
    expect = [p for p in positions if parse_line(p) is not None]
    assert len(got) == len(expect), ("line count", len(got), len(expect), positions[:20])
    for line, pos in zip(got, expect, strict=False):
        gaps = parse_line(pos)
        truth = search_call(gaps, nudge) if (brute and in_range(gaps, span)) else None
        check_output_line(line, gaps, span, nudge=nudge, truth=truth)
    return got


# ----- the reckoning against the full game search ----------------------------


def test_reckoning_matches_the_search():
    """The closed reckoning over the rooms must agree with a full game search that knows
    no shortcut, on every board of up to four discs of at most eight spaces of room, with no
    nudge. This pins the winning rule, including that the alternation is counted from the back of
    the line and swings with the count of discs."""
    for n in range(5):
        for combo in itertools.product(range(9), repeat=n):
            gaps = list(combo)
            assert search_call(gaps) == call_of(gaps), (gaps, call_of(gaps))


def test_reckoning_matches_the_search_under_a_nudge():
    """The same cross-check under a nudge. For each of several nudges, every board of up to four
    discs of at most eight spaces is played out in full and the capped reckoning must agree. This
    pins that the nudge feeds into the reckoning: a build that ignores it fails a good many."""
    for nudge in (0, 1, 2, 3, 4):
        for n in range(5):
            for combo in itertools.product(range(9), repeat=n):
                gaps = list(combo)
                assert search_call(gaps, nudge) == call_of(gaps, nudge), \
                    (gaps, nudge, call_of(gaps, nudge))


def test_tool_matches_reckoning_on_small_batch():
    """Every board of up to four discs of at most six spaces, fed as one batch and each call
    and shove checked against the reckoning. A build that reads each room as an independent
    heap, or that fixes the alternation from the ledge, gets a good many of these wrong."""
    positions = [" ".join(str(x) for x in combo)
                 for n in range(5)
                 for combo in itertools.product(range(7), repeat=n)]
    check_batch(None, positions)


def test_tool_matches_reckoning_on_small_batch_under_a_nudge():
    """Every board of up to four discs of at most six spaces, fed at a road with a small nudge and
    checked against the capped reckoning. A build that ignores the nudge, weighing the raw
    rooms, calls a large share of these backwards."""
    positions = [" ".join(str(x) for x in combo)
                 for n in range(5)
                 for combo in itertools.product(range(7), repeat=n)]
    for nudge in (1, 2, 3):
        check_batch(None, positions, nudge=nudge)


def test_tool_matches_search_board_by_board():
    """Every board of up to three discs of at most six spaces, each cross-checked against a full
    game search, with no nudge and again under a nudge. This pins the call and the shove straight
    against played-out truth."""
    positions = [" ".join(str(x) for x in combo)
                 for n in range(4)
                 for combo in itertools.product(range(7), repeat=n)]
    check_batch(None, positions, brute=True)
    for nudge in (1, 2, 4):
        check_batch(None, positions, nudge=nudge, brute=True)


# ----- the nudge, which the naive readings all miss ---------------------------


def test_nudge_makes_multiples_of_the_stride_a_loss():
    """A lone disc whose room is a whole number of full strides, a stride being the nudge plus
    one, is a loss under that nudge: the player to move can only crawl it and hands the scoring
    shove to the other. A plain heap reading and a staircase reading that ignore the nudge both call
    every lone disc a win. Off a full stride the board is a win."""
    cases = [
        (1, ["2", "4", "6", "8", "20"], ["1", "3", "5", "7", "21"]),
        (2, ["3", "6", "9", "12"], ["1", "2", "4", "5", "7"]),
        (3, ["4", "8", "12", "40"], ["1", "2", "3", "5", "6", "7"]),
        (4, ["5", "10", "15"], ["1", "4", "6", "9", "11"]),
    ]
    for nudge, losses, wins in cases:
        got = run_bin(None, losses + wins, nudge=nudge)
        for k, case in enumerate(losses):
            gaps = [int(case)]
            assert got[k] == case + " | STUCK", (nudge, got[k], "expected STUCK")
            assert search_call(gaps, nudge) == "STUCK", (nudge, case)
        for k, case in enumerate(wins):
            line = got[len(losses) + k]
            gaps = [int(case)]
            assert line.startswith(case + " | FORCED "), (nudge, line, "expected FORCED")
            check_output_line(line, gaps, None, nudge=nudge,
                              truth=("FORCED" if gaps[0] <= 8 else None))


def test_nudge_flips_the_call_from_no_cap():
    """The very same boards read one way with no cap and the other way under a nudge. Pinned under
    the nudge, so a build that never folds the nudge into the reckoning fails one side of each
    pair. Each capped call is cross-checked against a full game search."""
    pairs = [
        (1, "2", "STUCK"), (1, "3 3", "FORCED"), (1, "1 1", "FORCED"),
        (2, "3", "STUCK"), (2, "4 1", "FORCED"), (2, "5 8 2", "STUCK"),
        (2, "6 3", "STUCK"), (3, "4 4 4", "STUCK"), (3, "5 1", "FORCED"),
        (1, "0 2", "STUCK"), (1, "0 3", "FORCED"),
    ]
    for nudge, case, want in pairs:
        gaps = [int(x) for x in case.split()]
        assert search_call(gaps, nudge) == want, (nudge, case, "search")
        got = run_bin(None, [case], nudge=nudge)
        if want == "STUCK":
            assert got == [case + " | STUCK"], (nudge, got)
        else:
            assert got[0].startswith(case + " | FORCED "), (nudge, got)
            check_output_line(got[0], gaps, None, nudge=nudge, truth="FORCED")


def test_nudge_gates_the_scoring_shove():
    """A front disc standing farther off the ledge than the nudge cannot be scored on one turn, so a
    winning shove on it can spend at most the nudge. Every reported shove is replayed and required to
    be within the nudge and to leave a loss; a build that scores a far front disc in a single shove
    names an illegal move here."""
    cases = [(2, "7 2 1"), (2, "5 3"), (3, "10 1 2"), (1, "6 1"), (3, "8 8 8 1")]
    for nudge, case in cases:
        gaps = [int(x) for x in case.split()]
        got = run_bin(None, [case], nudge=nudge)
        assert len(got) == 1, got
        check_output_line(got[0], gaps, None, nudge=nudge,
                          truth=(search_call(gaps, nudge) if sum(gaps) <= 24 else None))


def test_nudge_zero_forbids_every_shove():
    """A nudge of nought lets no disc move at all, so every board, with room or not, is a loss for
    the player to move."""
    got = run_bin(None, ["0", "1", "5", "3 4", "0 0 2", "9 9 9"], nudge=0)
    assert got == ["0 | STUCK", "1 | STUCK", "5 | STUCK", "3 4 | STUCK",
                   "0 0 2 | STUCK", "9 9 9 | STUCK"], got


def test_valid_huge_nudge_behaves_like_no_cap():
    """A nudge at the top of the signed 64-bit range is wider than any room can be, so it
    caps nothing and the road plays as if no nudge were set. This pins the stride against an
    overflow at the boundary and checks large rooms are shoved correctly under a nudge."""
    huge = 2 ** 63 - 1
    cases = ["1", "5", "1000000000000", "0 7", "6 6", "3 5 2", str(2 ** 62), "0 " + str(huge)]
    got = run_bin(None, cases, nudge=huge)
    assert len(got) == len(cases), got
    for k, case in enumerate(cases):
        gaps = [int(x) for x in case.split()]
        assert weigh(gaps, huge) == weigh(gaps), (case, "huge nudge should match no cap")
        check_output_line(got[k], gaps, None, nudge=huge)


def test_nudge_and_span_together():
    """A road that sets both a room span and a shove nudge. Out-of-range boards are still
    called VOID, and the in-range boards are judged under the nudge. A disc above the span is
    out of range even though the nudge would let it be crawled."""
    got = run_bin(20, ["3", "5", "21", "4 4", "8 8 8"], nudge=2)
    assert got[0] == "3 | STUCK", got
    assert got[1].startswith("5 | FORCED "), got
    assert got[2] == "21 | VOID", got
    check_batch(20, ["3", "5", "21", "4 4", "8 8 8", "0 6"], nudge=2)


# ----- the decisive boards (no cap) -------------------------------------------


def test_front_disc_at_the_ledge_flips_the_call():
    """A front disc already snug against the ledge, with a disc behind it that still has room.
    A reading that fixes the alternation from the ledge weighs the snug front room and
    drops the disc that actually bears, calling these a loss; played out they are a win, and the
    shove is on the disc behind. Same boards, opposite call."""
    for case in ["0 1", "0 2", "0 3", "0 5", "0 0 0 3", "0 0 0 5", "0 3 0 2"]:
        got = run_bin(None, [case])
        gaps = [int(x) for x in case.split()]
        assert win_search(gaps), (case, "expected a win")
        assert len(got) == 1 and got[0].startswith(case + " | FORCED "), got
        check_output_line(got[0], gaps, None, truth="FORCED")


def test_snug_disc_behind_the_leader_is_a_loss():
    """A front disc with room and the disc behind it snug against it. There is an even count of
    discs, so the room that bears is the snug one at the back and the board is a loss; a
    reading that folds every room as its own heap, or that alternates from the ledge, weighs
    the front disc and calls it a win. Played out, the player to move loses."""
    for case in ["1 0", "2 0", "3 0", "5 0", "6 0", "0 1 1 1", "0 2 3 2", "5 3 1 3"]:
        got = run_bin(None, [case])
        gaps = [int(x) for x in case.split()]
        assert not win_search(gaps), (case, "expected a loss")
        assert got == [case + " | STUCK"], got


def test_equal_rooms_pair_is_a_win():
    """Two discs with equal room. Folding both as independent heaps cancels them and reads
    a loss, but the pair is a win: only the back disc bears, and shoving it to snug lands the
    other player a loss. A plain independent-heap reading calls these backwards."""
    for case in ["1 1", "2 2", "3 3", "4 4", "7 7", "31 31"]:
        got = run_bin(None, [case])
        gaps = [int(x) for x in case.split()]
        assert win_search(gaps) if max(gaps) <= 8 else True
        assert len(got) == 1 and got[0].startswith(case + " | FORCED "), got
        check_output_line(got[0], gaps, None)


def test_even_and_odd_disc_counts_read_apart():
    """The same three rooms read one way with an even count of discs and the other way with
    an odd count. A build that fixes the alternation from the ledge cannot tell the two apart and
    fails one of them."""
    check_batch(None, ["4 4 4", "0 4 4 4", "1 2 3", "0 1 2 3", "6 3 5", "0 6 3 5",
                       "2 5 6 3", "5 6 3", "7 1 6 1", "1 6 1"], brute=False)


def test_scoring_move_can_be_the_win():
    """Boards whose winning shove spends the front disc's whole room, scoring it at the ledge
    and dropping the line by a disc. The reported shove is replayed and required to leave a loss,
    so a build that never lets the front disc reach the ledge cannot answer these. The shoved
    distance equals the front disc's room, which is what scores it."""
    for case in ["3 5 0", "4 2 0", "5 1 0", "2 7 0", "6 3 0"]:
        got = run_bin(None, [case])
        assert len(got) == 1, got
        gaps = [int(x) for x in case.split()]
        assert search_call(gaps) == call_of(gaps), case
        assert got[0] == case + f" | FORCED shove disc 1 forward {gaps[0]}", got
        check_output_line(got[0], gaps, None, truth="FORCED")


# ----- snug and single boards ------------------------------------------------


def test_all_snug_is_a_loss():
    """A board where every disc is snug, front against the ledge and each other against its
    leader, has no shove to make and is a loss with no move."""
    assert run_bin(None, ["0"]) == ["0 | STUCK"]
    assert run_bin(None, ["0 0"]) == ["0 0 | STUCK"]
    assert run_bin(None, ["0 0 0"]) == ["0 0 0 | STUCK"]
    assert run_bin(None, ["0 0 0 0"]) == ["0 0 0 0 | STUCK"]


def test_single_disc_on_its_own_is_a_win():
    """With no cap a lone disc with room, whatever its room, is a win: the player to move
    shoves it the whole way to the ledge, scores it, and there is no disc left to move. Checked
    against the search on the small ones and by replay on the larger."""
    for case in ["1", "2", "3", "4", "5", "6", "7", "8", "20", "511"]:
        got = run_bin(None, [case])
        gaps = [int(x) for x in case.split()]
        assert len(got) == 1 and got[0].startswith(case + " | FORCED "), got
        check_output_line(got[0], gaps, None,
                          truth=("FORCED" if gaps[0] <= 8 else None))


# ----- larger winning boards past the search ----------------------------------


def test_larger_winning_boards():
    """Wider winning boards well past any game search, each labelled by the reckoning. Every
    reported winning shove is replayed to confirm it leaves a loss, so a build that mislocates
    which room bears or botches the shove on bigger discs fails."""
    cases = ["259 4 3", "1027 3 4 9", "512 513", "515 516 20", "1023 1024",
             "1 6 1026 8", "700 701 3", "2046 3 4", "6 10 12 5", "0 20 24 7 9"]
    for case in cases:
        got = run_bin(None, [case])
        assert len(got) == 1, got
        gaps = [int(x) for x in case.split()]
        assert weigh(gaps) != 0, (case, "should be a win")
        check_output_line(got[0], gaps, None)


def test_larger_winning_boards_under_a_nudge():
    """Wide boards at a road with a nudge, labelled by the capped reckoning and every reported shove
    replayed within the nudge. A build that ignores the nudge names a wrong call or an illegal
    shove on these."""
    cases = [(3, "259 4 3"), (5, "1027 3 4 9"), (2, "515 516 20"), (7, "1 6 1026 8"),
             (4, "700 701 3"), (6, "6 10 12 5"), (3, "0 20 24 7 9"), (2, "13 40 5")]
    for nudge, case in cases:
        gaps = [int(x) for x in case.split()]
        if weigh(gaps, nudge) == 0:
            continue
        got = run_bin(None, [case], nudge=nudge)
        assert len(got) == 1, got
        check_output_line(got[0], gaps, None, nudge=nudge)


# ----- out-of-range boards ----------------------------------------------------


def test_over_the_span_is_illegal():
    """A disc above the room span puts the board out of range: it is echoed and reported
    VOID with no call. Discs at or under the span play normally."""
    got = run_bin(10, ["11", "10", "0 11", "5 20", "10 10", "3 4 5"])
    assert got[0] == "11 | VOID", got
    assert got[1] != "10 | VOID", got
    assert got[2] == "0 11 | VOID", got
    assert got[3] == "5 20 | VOID", got
    assert got[4] != "10 10 | VOID", got
    assert got[5] != "3 4 5 | VOID", got
    check_batch(10, ["11", "10", "0 11", "5 20", "10 10", "3 4 5"])


def test_negative_is_out_of_range_not_skipped():
    """A negative field is a whole number all the same: it is read, judged out of range, and the
    board is echoed and reported VOID. It is never treated as junk and never dropped on that
    account."""
    got = run_bin(None, ["-1", "-1 2", "3 -5 4", "0 -1"])
    assert got == ["-1 | VOID", "-1 2 | VOID", "3 -5 4 | VOID", "0 -1 | VOID"], got


def test_number_out_of_range_versus_not_a_number():
    """-1 is a number out of range and is reported; x is not a number and the line is dropped.
    Fed together, only the -1 line and the 2 3 line come back."""
    got = run_bin(None, ["-1", "x", "1 y", "2 3"])
    assert len(got) == 2, got
    assert got[0] == "-1 | VOID", got
    assert got[1].startswith("2 3 | FORCED "), got
    check_output_line(got[1], [2, 3], None)


def test_non_numeric_and_blank_lines_skipped():
    """Blank lines and lines carrying a field that is not a whole-number literal are dropped
    with no output. A decimal point, an underscore, a hex marker and a letter are all not
    whole-number literals."""
    got = run_bin(None, ["", "   ", "3 x 5", "1 2 3.0", "1_000", "0x4", "1 2 5"])
    assert len(got) == 1, got
    assert got[0].startswith("1 2 5 | "), got
    check_output_line(got[0], [1, 2, 5], None)


def test_oversized_literals_are_skipped():
    """A run of digits too large to fit a signed 64-bit integer is not a whole-number literal,
    so a line carrying one is skipped with no output, the same as any other non-literal field."""
    big = "9" * 25
    got = run_bin(None, [big, "-" + big, big + " 2", "1 2 5"])
    assert len(got) == 1, got
    assert got[0].startswith("1 2 5 | "), got
    check_output_line(got[0], [1, 2, 5], None)


def test_int64_boundary_literals():
    """The boundary of a signed 64-bit integer. The largest and smallest values that fit are
    whole-number literals and are read, then judged out of range under this road; a value one
    past either end does not fit, so its line is skipped."""
    got = run_bin(100, ["9223372036854775807", "9223372036854775808",
                        "-9223372036854775808", "-9223372036854775809", "3 4"])
    assert got[0] == "9223372036854775807 | VOID", got
    assert got[1] == "-9223372036854775808 | VOID", got
    assert got[2].startswith("3 4 | "), got
    check_output_line(got[2], [3, 4], 100)


# ----- echo ------------------------------------------------------------------


def test_malformed_signs():
    """A whole-number literal carries at most one leading sign. A doubled or crossed sign is not
    a literal, so the line is skipped. A signed zero is the number nought and plays."""
    got = run_bin(None, ["++1", "--1", "+-1", "1 +-2", "-0", "+0"])
    assert got == ["0 | STUCK", "0 | STUCK"], got


def test_echo_normalizes_spacing_and_signs():
    """The echoed board is the rooms as numbers, one space apart. Runs of blanks collapse,
    leading and trailing blanks go, leading zeros drop and a leading plus drops, and the
    call still has to match the reckoning on the same line."""
    got = run_bin(None, ["  3    4  5 ", "007 0", "+3 5"])
    assert got[0].startswith("3 4 5 | "), got
    assert got[1].startswith("7 0 | "), got
    assert got[2].startswith("3 5 | "), got
    check_batch(None, ["  3    4  5 ", "007 0", "+3 5"])


# ----- board-file parsing -----------------------------------------------------


def test_default_is_no_span():
    """A board file that sets nothing leaves the span unset, so even very wide rooms are in
    range and the line is answered rather than voided."""
    got = run_bin_text("# a note, nothing set\n", ["1000 2000"])
    assert got[0] != "1000 2000 | VOID", got
    check_output_line(got[0], [1000, 2000], None)


def test_last_span_value_wins():
    """A board file may carry several span lines. The last one stands, so a room of fifty is
    in range after 5 then 100 and out of range after 100 then 5."""
    got = run_bin_text("span: 5\nspan: 100\n", ["50"])
    assert len(got) == 1 and got[0].startswith("50 | FORCED "), got
    check_output_line(got[0], [50], None)
    got = run_bin_text("span: 100\nspan: 5\n", ["50"])
    assert got == ["50 | VOID"], got


def test_span_ignores_non_digit_and_signed_words():
    """A span word that is not a run of decimal digits, a word or a signed number, leaves the
    span where it stood. Extra words after a good span value are ignored and the value
    still takes."""
    got = run_bin_text("span: five\n", ["500"])
    assert got[0] != "500 | VOID", got
    got = run_bin_text("span: -3\n", ["500"])
    assert got[0] != "500 | VOID", got
    got = run_bin_text("span: 5 spaces please\n", ["3", "6"])
    assert got[0].startswith("3 | FORCED "), got
    assert got[1] == "6 | VOID", got


def test_comment_stripped_from_span_line():
    """A comment after the span value is cut before the value is read, so the span is the
    number alone and boards are judged against it."""
    got = run_bin_text("span: 5   # a small road\n", ["3", "6"])
    assert got[0].startswith("3 | FORCED "), got
    assert got[1] == "6 | VOID", got


def test_span_zero_allows_only_snug_discs():
    """A span of nought puts every disc holding any room out of range, so only boards whose
    discs are all snug are answered and the rest are voided."""
    got = run_bin_text("span: 0\n", ["0", "0 0", "1", "0 1"])
    assert got == ["0 | STUCK", "0 0 | STUCK", "1 | VOID", "0 1 | VOID"], got


# ----- nudge-line parsing -----------------------------------------------------


def test_default_is_no_nudge():
    """With no nudge line the road puts no cap on a shove, so a lone disc is a win whatever its
    room and the front disc may be scored from any distance."""
    got = run_bin_text("# nothing set\n", ["4", "6", "9"])
    assert got[0].startswith("4 | FORCED "), got
    assert got[1].startswith("6 | FORCED "), got
    assert got[2].startswith("9 | FORCED "), got
    check_output_line(got[0], [4], None)


def test_nudge_line_sets_the_cap():
    """A nudge line caps the shove. Under nudge 1 a lone disc of room two is a loss where with
    no nudge it is a win, which pins that the nudge line is read and folded in."""
    got = run_bin_text("nudge: 1\n", ["2", "4", "3"])
    assert got == ["2 | STUCK", "4 | STUCK", "3 | FORCED shove disc 1 forward 1"], got


def test_last_nudge_value_wins():
    """A board file may carry several nudge lines. The last one stands, so a room of four is
    a win after 1 then 5 and a loss after 5 then 1."""
    got = run_bin_text("nudge: 1\nnudge: 5\n", ["4"])
    assert got[0].startswith("4 | FORCED "), got
    check_output_line(got[0], [4], None, nudge=5)
    got = run_bin_text("nudge: 5\nnudge: 1\n", ["4"])
    assert got == ["4 | STUCK"], got


def test_nudge_ignores_non_digit_and_signed_and_oversize_words():
    """A nudge word that is not a run of decimal digits, whether a word, a signed number, or a run
    too large to fit a signed 64-bit integer, leaves the nudge where it stood. Set after a good
    nudge, the good one stands."""
    got = run_bin_text("nudge: two\n", ["2"])
    assert got[0].startswith("2 | FORCED "), got
    got = run_bin_text("nudge: -1\n", ["2"])
    assert got[0].startswith("2 | FORCED "), got
    got = run_bin_text("nudge: 1\nnudge: 9223372036854775808\n", ["2", "3"])
    assert got == ["2 | STUCK", "3 | FORCED shove disc 1 forward 1"], got


def test_comment_and_whitespace_on_the_nudge_line():
    """The nudge line is read after a comment is cut and leading blanks are trimmed, and a tab
    after the colon is fine. A blank before the colon is not the nudge key, so that line
    sets nothing."""
    got = run_bin_text("nudge: 1   # short shoves only\n", ["2", "3"])
    assert got == ["2 | STUCK", "3 | FORCED shove disc 1 forward 1"], got
    got = run_bin_text("   nudge:\t1\n", ["2"])
    assert got == ["2 | STUCK"], got
    got = run_bin_text("nudge : 1\n", ["2"])
    assert got[0].startswith("2 | FORCED "), got


def test_span_and_nudge_lines_are_independent():
    """A road may set the span, the nudge, both, or neither, each from its own line. Set
    together, a board is judged under the nudge and called out only when a room breaks the
    span."""
    got = run_bin_text("span: 10\nnudge: 2\n", ["3", "5", "11", "9 9"])
    assert got[0] == "3 | STUCK", got
    assert got[1].startswith("5 | FORCED "), got
    assert got[2] == "11 | VOID", got
    check_batch(10, ["3", "5", "11", "9 9", "0 6 3"], nudge=2)


# ----- exit codes ------------------------------------------------------------


def test_missing_argument_exits_two():
    """Run with no board file at all, the tool exits two and prints nothing on standard output."""
    p = sandboxed([BIN], "1\n", timeout=10.0)
    assert p.returncode == 2, f"expected exit 2, got {p.returncode}"
    assert p.stdout == "", repr(p.stdout)


def test_extra_argument_exits_two():
    """Run with more than one argument, the tool exits two and prints nothing on standard output."""
    p = sandboxed([BIN, "a", "b"], "1\n", timeout=10.0)
    assert p.returncode == 2, f"expected exit 2, got {p.returncode}"
    assert p.stdout == "", repr(p.stdout)


def test_unreadable_board_file_exits_two():
    """A board path that cannot be opened exits two and prints nothing on standard output."""
    p = sandboxed([BIN, "/no/such/board/file"], "1\n", timeout=10.0)
    assert p.returncode == 2, f"expected exit 2, got {p.returncode}"
    assert p.stdout == "", repr(p.stdout)


def test_board_path_that_is_a_directory_exits_two():
    """A directory handed over in place of a board file exits two and prints nothing on
    standard output."""
    d = tempfile.mkdtemp(prefix="garnet-board-watch-")
    try:
        os.chmod(d, 0o755)
        p = sandboxed([BIN, d], "1\n", timeout=10.0)
        assert p.returncode == 2, f"expected exit 2, got {p.returncode}"
        assert p.stdout == "", repr(p.stdout)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_good_run_exits_zero():
    """A readable board file and one good line exit zero, print exactly one output line ending
    in a newline, and the call on that line matches the reckoning under the road's nudge."""
    root = tempfile.mkdtemp(prefix="garnet-board-watch-")
    try:
        os.chmod(root, 0o755)
        path = os.path.join(root, "board.txt")
        pathlib.Path(path).write_text("span: 10\nnudge: 3\n", encoding="utf-8")
        os.chmod(path, 0o644)
        p = sandboxed([BIN, path], "1 2 5\n", timeout=10.0)
        assert p.returncode == 0, f"expected exit 0, got {p.returncode}"
        lines = p.stdout.split("\n")
        assert len(lines) == 2 and lines[1] == "", repr(p.stdout)
        assert lines[0].startswith("1 2 5 | "), repr(p.stdout)
        check_output_line(lines[0], [1, 2, 5], None, nudge=3)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ----- random differentials --------------------------------------------------


def rand_small(rng):
    """A random board small enough to be played out by the search, rooms drawn to favour
    snug discs and near-equal pairs."""
    n = rng.randint(0, 5)
    gaps = [rng.choice([0, 0, 1, 1, 2, 3, 4, 5, 6, 6, 7, 7, 8]) for _ in range(n)]
    return " ".join(str(g) for g in gaps)


def test_random_small_batches_match_the_reckoning():
    """Random small boards, every call and shove checked against the reckoning. A build that
    folds independent heaps, or that fixes the alternation from the ledge, fails."""
    rng = random.Random(80531)
    positions = [rand_small(rng) for _ in range(600)]
    check_batch(None, positions)


def test_random_small_singles_match_the_search():
    """The same shape of random small boards, each cross-checked against the full game search to
    pin the call straight against played-out truth, with no nudge and again under a nudge."""
    rng = random.Random(6021)
    positions = [rand_small(rng) for _ in range(400)]
    check_batch(None, positions, brute=True)
    rng = random.Random(6022)
    positions = [rand_small(rng) for _ in range(400)]
    for nudge in (1, 2, 3):
        check_batch(None, positions, nudge=nudge, brute=True)


def rand_wide(rng):
    """A random board too wide to play out, for checking the reckoning against the tool alone."""
    n = rng.randint(1, 9)
    vmax = rng.choice([15, 31, 63, 127, 255, 511, 1023, 2047])
    gaps = [rng.randint(0, vmax) for _ in range(n)]
    return " ".join(str(g) for g in gaps)


def test_random_wide_batches_match_the_reckoning():
    """Wider boards past any game search: the reckoning labels them and every reported winning
    shove is replayed and checked, with no nudge and under a mix of nudges."""
    rng = random.Random(20719)
    positions = [rand_wide(rng) for _ in range(600)]
    check_batch(None, positions)
    rng = random.Random(20720)
    for nudge in (1, 2, 5, 12, 100):
        positions = [rand_wide(rng) for _ in range(200)]
        check_batch(None, positions, nudge=nudge)


def rand_front_snug(rng):
    """Boards that lead with a snug disc, where a reading fixed from the ledge is easiest to get
    backwards."""
    n = rng.randint(1, 5)
    gaps = [0] + [rng.choice([0, 1, 2, 3, 4, 5, 6, 7]) for _ in range(n)]
    return " ".join(str(g) for g in gaps)


def test_random_front_snug_boards():
    """Boards leading with a snug front disc, checked against the reckoning where the alternation
    from the ledge reads the wrong set of rooms, with and without a nudge."""
    rng = random.Random(4095)
    positions = [rand_front_snug(rng) for _ in range(500)]
    check_batch(None, positions)
    rng = random.Random(4096)
    positions = [rand_front_snug(rng) for _ in range(300)]
    for nudge in (1, 2, 3):
        check_batch(None, positions, nudge=nudge)


def test_random_with_a_span_mixes_illegal():
    """Random boards at a road with a span, so a mix of legal and out-of-range boards come
    together: the line count and the VOID reports are pinned alongside the calls."""
    rng = random.Random(272727)
    positions = []
    for _ in range(400):
        n = rng.randint(1, 5)
        positions.append(" ".join(str(rng.randint(0, 560)) for _ in range(n)))
    check_batch(512, positions)


def test_random_with_a_span_and_a_nudge():
    """Random boards at a road that sets both a span and a nudge: illegal boards are still called
    out, and the legal ones are judged under the nudge."""
    rng = random.Random(515151)
    positions = []
    for _ in range(400):
        n = rng.randint(1, 5)
        positions.append(" ".join(str(rng.randint(0, 560)) for _ in range(n)))
    check_batch(512, positions, nudge=7)


# ----- long boards ------------------------------------------------------------


def test_long_boards_match_the_reckoning():
    """Boards with many discs, well past any game search and long enough that a whole board runs
    past sixty kilobytes on one line, labelled by the reckoning and every reported shove replayed,
    with no nudge and under a nudge. A build that plays each board out disc by disc cannot answer
    these; the reckoning reads them at a glance and the shove must still land the other player a
    loss."""
    rng = random.Random(9137)
    positions = []
    for _ in range(6):
        n = rng.randint(2000, 4000)
        positions.append(" ".join(str(rng.randint(0, (1 << 40))) for _ in range(n)))
    # one very long single board, over sixty kilobytes of rooms on a line
    positions.append(" ".join(str(rng.randint(0, 999999)) for _ in range(20000)))
    check_batch(None, positions)
    check_batch(None, positions, nudge=97)


def test_input_without_a_final_newline():
    """A board fed with no closing newline is still read and answered, the same as one that ends
    the input with a newline."""
    root = tempfile.mkdtemp(prefix="garnet-board-watch-")
    try:
        os.chmod(root, 0o755)
        path = os.path.join(root, "board.txt")
        pathlib.Path(path).write_text("span: 10\n", encoding="utf-8")
        os.chmod(path, 0o644)
        p = sandboxed([BIN, path], "1 2 5", timeout=10.0)
        assert p.returncode == 0, (p.returncode, p.stderr[:300])
        lines = p.stdout.split("\n")
        assert len(lines) == 2 and lines[1] == "", repr(p.stdout)
        assert lines[0].startswith("1 2 5 | "), repr(p.stdout)
        check_output_line(lines[0], [1, 2, 5], None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ----- more board-file parsing ------------------------------------------------


def test_oversize_span_leaves_the_prior_value():
    """A span word that is a run of digits but too large to fit a signed 64-bit integer is not
    a value: it leaves the setting where it stood. Set after a good span, the good one stands."""
    got = run_bin_text("span: 5\nspan: 9223372036854775808\n", ["5", "6"])
    assert got[0].startswith("5 | FORCED "), got
    assert got[1] == "6 | VOID", got
    got = run_bin_text("span: 5\nspan: 99999999999999999999999\n", ["6"])
    assert got == ["6 | VOID"], got


def test_span_line_whitespace_variants():
    """A span line is recognized after leading whitespace is trimmed, and the value may sit
    behind a tab. A word with a space before the colon does not begin with span: and is not a
    span line, so it leaves the setting unset."""
    got = run_bin_text("   span: 7\n", ["7", "8"])
    assert got[0].startswith("7 | FORCED "), got
    assert got[1] == "8 | VOID", got
    got = run_bin_text("span:\t7\n", ["8"])
    assert got == ["8 | VOID"], got
    got = run_bin_text("span : 7\n", ["8"])
    assert got[0] != "8 | VOID", got


# ----- the verifier stays out of reach --------------------------------------


def test_engine_cannot_read_the_verifier():
    """Everything the engine runs as is barred from the verifier's files, so an engine cannot
    read this reference and print its answers instead of settling the boards. Guards the isolation
    itself: if the lockdown in test.sh ever stops taking effect, this fails rather than quietly
    letting a delegating solution through."""
    p = sandboxed(["/bin/cat", os.path.abspath(__file__)], "", timeout=20.0)
    assert p.returncode != 0, "the verifier's own test file was readable"
    assert "search_call" not in p.stdout, "the reference leaked to the engine"
