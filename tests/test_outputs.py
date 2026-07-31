import operator
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CERTIFIED_BRACKETS = Path(__file__).resolve().parent / "fixtures"
BRACKET_TOOL = os.environ.get("REFEREE_BIN", "/app/bin/hallowspar")
BRACKET_TOOL_SRC = os.environ.get("REFEREE_SRC", "/app/opt/hallowspar")
FIRST_CROWN = os.environ.get("CROWN_MAIN_ROOT", "/app/crown")
OTHER_CROWN = str(CERTIFIED_BRACKETS / "corveholt")

BERTH_LADDER = ("CROWNED", "UPSET", "RESTED", "VACATED", "DARK")
HOUSE_LADDER_ORDER = ("CROWNED", "BARRED", "CUT", "FELLED", "SEATED")
BERTH_BLOCK_HEAD = "-- berths --"
HOUSE_BLOCK_LINE = "-- houses --"

_brackets_filed = {}


def invoke_bracket_tool(root, target, flags=()):
    where = dict(os.environ)
    where["RECORD_ROOT"] = str(root)
    where["CLOSING_SHEET"] = str(target)
    return subprocess.run(
        [BRACKET_TOOL, *flags],
        capture_output=True,
        text=True,
        env=where,
        check=False,
    )


def file_one_bracket(root, flags=()):
    home = tempfile.mkdtemp(prefix="crown-")
    target = Path(home) / "filed" / "closing-sheet.txt"
    done = invoke_bracket_tool(root, target, flags)
    return done, target, home


def settled_bracket(root):
    key = str(root)
    if key not in _brackets_filed:
        done, target, _home = file_one_bracket(key)
        assert done.returncode == 0, done.stderr
        _brackets_filed[key] = target.read_text(encoding="ascii")
    return _brackets_filed[key]


def certified_bracket(name):
    return (CERTIFIED_BRACKETS / name).read_text(encoding="ascii")


def replanted_crown(root, steps, widths=None):
    home = tempfile.mkdtemp(prefix="replayed-")
    laid = Path(home) / "crown"
    shutil.copytree(root, laid)
    body = "".join(f"{number} {line}\n" for number, line in enumerate(steps, 1))
    (laid / "record" / "crown.log").write_text(body, encoding="ascii")
    if widths is not None:
        (laid / "widths.table").write_text(
            "".join(f"{index} {width}\n" for index, width in enumerate(widths, 1)),
            encoding="ascii")
    done, target, _home = file_one_bracket(str(laid))
    assert done.returncode == 0, done.stderr
    return target.read_text(encoding="ascii")


def column_one_of(root, name):
    rows = []
    for raw in (Path(root) / name).read_text(encoding="ascii").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            rows.append(line.split()[0])
    return rows


def carve_bracket(text):
    lines = text.rstrip("\n").split("\n")
    head = lines[0].split()
    berths = int(head[head.index("berths") + 1])
    houses = int(head[head.index("houses") + 1])
    berth_rows = [line.split() for line in lines[2 : 2 + berths]]
    first = 3 + berths
    house_rows = [line.split() for line in lines[first : first + houses]]
    return lines, berth_rows, house_rows


def head_tally_of(text, word):
    head = text.split("\n")[0].split()
    return int(head[head.index(word) + 1])


def berth_entry(text, name):
    _lines, berth_rows, _house_rows = carve_bracket(text)
    for row in berth_rows:
        if row[0] == name:
            return row
    message = "no line for the berth " + name
    raise AssertionError(message)


def house_entry(text, name):
    _lines, _berth_rows, house_rows = carve_bracket(text)
    for row in house_rows:
        if row[0] == name:
            return row
    message = "no line for the house " + name
    raise AssertionError(message)


sitting_house = operator.itemgetter(2)


def berth_board_count(row):
    return int(row[4])


def berth_hand_count(row):
    return int(row[6])


def opening_seed(row):
    return int(row[2])


def wins_held(row):
    return int(row[4])


def losses_held(row):
    return int(row[6])


def meetings_held(row):
    return int(row[8])


def strength_held(row):
    return int(row[10])


def hands_taken(row):
    return int(row[12])


def hands_given(row):
    return int(row[14])


berth_held = operator.itemgetter(16)


def place_held(row):
    return int(row[18])


place_rule = operator.itemgetter(19)


settled_state = operator.itemgetter(-2)


settled_token = operator.itemgetter(-1)


def tally_counts(text, label):
    for line in text.rstrip("\n").split("\n"):
        if line.startswith(label + " "):
            fields = line.split()[1:]
            return {fields[i]: int(fields[i + 1]) for i in range(0, len(fields), 2)}
    message = "no tally line for " + label
    raise AssertionError(message)


def test_certified_sheet_of_the_recorded_crown():
    """Matches the whole filed sheet for the recorded crown against its certified copy."""
    assert settled_bracket(FIRST_CROWN) == certified_bracket("certified-hallowspar.txt")


def test_certified_sheet_of_the_second_crown():
    """Matches the whole filed sheet for the other recorded crown, byte for byte."""
    assert settled_bracket(OTHER_CROWN) == certified_bracket("certified-corveholt.txt")


def test_repeat_filing_of_the_recorded_crown_agrees():
    """Checks the repeat filing over an unchanged record for the recorded crown."""
    done, target, _home = file_one_bracket(FIRST_CROWN, ("--selfcheck",))
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""
    assert done.stderr == ""
    assert target.read_text(encoding="ascii") == certified_bracket("certified-hallowspar.txt")


def test_repeat_filing_of_the_second_crown_agrees():
    """Checks the repeat filing over an unchanged record for the other crown."""
    done, target, _home = file_one_bracket(OTHER_CROWN, ("--selfcheck",))
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""
    assert done.stderr == ""
    assert target.read_text(encoding="ascii") == certified_bracket("certified-corveholt.txt")


def test_the_wins_rung_lifts_a_house_over_a_smaller_count():
    """Examines how a larger count of wins weighs against a smaller one."""
    text = settled_bracket(FIRST_CROWN)
    lowen = house_entry(text, "lowen")
    ingle = house_entry(text, "ingle")
    assert place_held(lowen) < place_held(ingle)
    assert place_rule(lowen) == "place.wins"


def test_the_losses_rung_settles_houses_level_on_wins():
    """Examines how two houses level on wins are separated further down."""
    text = settled_bracket(FIRST_CROWN)
    ingle = house_entry(text, "ingle")
    hurst = house_entry(text, "hurst")
    assert wins_held(ingle) == wins_held(hurst) == 3
    assert losses_held(ingle) < losses_held(hurst)
    assert place_held(ingle) < place_held(hurst)
    assert place_rule(hurst) == "place.losses"


def test_the_strength_rung_settles_houses_level_higher_up():
    """Examines the rung reached when wins and losses both fail to separate."""
    text = settled_bracket(FIRST_CROWN)
    birling = house_entry(text, "birling")
    gorrel = house_entry(text, "gorrel")
    assert wins_held(birling) == wins_held(gorrel) == 5
    assert losses_held(birling) == losses_held(gorrel) == 3
    assert strength_held(birling) > strength_held(gorrel)
    assert settled_state(birling) == "CROWNED"
    assert settled_state(gorrel) == "CUT"
    assert place_rule(gorrel) == "place.strength"


def test_strength_adds_a_met_houses_wins_once_for_each_meeting():
    """Examines how a house met more than once weighs on the third rung."""
    text = settled_bracket(FIRST_CROWN)
    arden = house_entry(text, "arden")
    birling = house_entry(text, "birling")
    gorrel = house_entry(text, "gorrel")
    lowen = house_entry(text, "lowen")
    assert meetings_held(arden) == 4
    assert strength_held(arden) == wins_held(birling) + 2 * wins_held(gorrel) + wins_held(lowen)


def test_strength_goes_on_moving_after_a_house_has_gone():
    """Examines the third rung of a house whose opponents played on without it."""
    text = settled_bracket(FIRST_CROWN)
    ingle = house_entry(text, "ingle")
    hurst = house_entry(text, "hurst")
    lowen = house_entry(text, "lowen")
    birling = house_entry(text, "birling")
    assert settled_state(ingle) == "BARRED"
    assert strength_held(ingle) == wins_held(hurst) + 2 * wins_held(lowen) + wins_held(birling)
    assert strength_held(ingle) == 16


def test_the_worse_opening_seed_ranks_above_on_the_last_rung():
    """Examines which of two seeds ranks higher when nothing else separates."""
    text = settled_bracket(OTHER_CROWN)
    vessen = house_entry(text, "vessen")
    umber = house_entry(text, "umber")
    assert (wins_held(vessen), losses_held(vessen), strength_held(vessen)) == (0, 0, 0)
    assert (wins_held(umber), losses_held(umber), strength_held(umber)) == (0, 0, 0)
    assert opening_seed(vessen) > opening_seed(umber)
    assert place_held(vessen) < place_held(umber)
    assert place_rule(umber) == "place.seed"


def test_beating_a_house_does_not_order_the_two_of_them():
    """Examines whether one house beating another settles the order between them."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "seat rensham mid-2",
        "board far-1 near-3 9 1",
        "board near-3 near-1 9 1",
        "board far-1 mid-2 1 9",
        "board near-1 mid-2 9 1",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert (wins_held(sallow), losses_held(sallow), strength_held(sallow)) == (1, 1, 2)
    assert (wins_held(tarrant), losses_held(tarrant), strength_held(tarrant)) == (1, 1, 2)
    assert opening_seed(tarrant) > opening_seed(sallow)
    assert place_held(tarrant) < place_held(sallow)


def test_a_bye_leaves_the_meeting_count_where_it_was():
    """Examines what a free win does to the count of meetings and to a berth."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "bye",
    ])
    quinnel = house_entry(text, "quinnel")
    assert wins_held(quinnel) == 1
    assert meetings_held(quinnel) == 0
    assert strength_held(quinnel) == 0
    assert berth_board_count(berth_entry(text, "near-1")) == 0
    assert berth_hand_count(berth_entry(text, "near-1")) == 0
    assert head_tally_of(text, "byes") == 1
    assert head_tally_of(text, "boards") == 0


def test_a_given_board_makes_a_meeting_for_one_side_only():
    """Examines which side of a board given up carries a meeting afterwards."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "concede far-1 near-3",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert (wins_held(sallow), losses_held(sallow), meetings_held(sallow)) == (0, 1, 1)
    assert (wins_held(tarrant), losses_held(tarrant), meetings_held(tarrant)) == (0, 0, 0)
    assert head_tally_of(text, "concedes") == 1


def test_a_seat_puts_a_house_into_a_berth_holding_none():
    """Examines the plain case of a house taking a berth nothing holds."""
    text = replanted_crown(OTHER_CROWN, ["seat sallow far-1"])
    assert sitting_house(berth_entry(text, "far-1")) == "sallow"
    assert berth_held(house_entry(text, "sallow")) == "far-1"
    assert settled_state(house_entry(text, "sallow")) == "SEATED"
    assert settled_token(house_entry(text, "sallow")) == "stand.seated"


def test_a_seat_at_a_berth_already_holding_one_reaches_nothing():
    """Examines a house sent to a berth another house is already sitting in."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant far-1",
    ])
    assert sitting_house(berth_entry(text, "far-1")) == "sallow"
    assert berth_held(house_entry(text, "tarrant")) == "-"
    assert settled_token(house_entry(text, "tarrant")) == "stand.unseated"


def test_a_seat_for_a_house_already_placed_still_names_the_berth():
    """Examines what a refused seating leaves behind at the berth it named."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat sallow near-3",
    ])
    assert sitting_house(berth_entry(text, "near-3")) == "-"
    assert settled_state(berth_entry(text, "near-3")) == "DARK"
    assert settled_token(berth_entry(text, "near-3")) == "dark.named"
    assert settled_token(berth_entry(text, "near-2")) == "dark.silent"


def test_a_board_enters_a_win_on_one_side_and_a_loss_on_the_other():
    """Examines what a decided board writes into the two records it touches."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 near-3 9 4",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert (wins_held(sallow), losses_held(sallow), meetings_held(sallow)) == (1, 0, 1)
    assert (wins_held(tarrant), losses_held(tarrant), meetings_held(tarrant)) == (0, 1, 1)
    assert head_tally_of(text, "boards") == 1


def test_a_board_enters_hands_taken_and_hands_given_both_ways():
    """Examines the two hand columns on each side of a decided board."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 near-3 9 4",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert (hands_taken(sallow), hands_given(sallow)) == (9, 4)
    assert (hands_taken(tarrant), hands_given(tarrant)) == (4, 9)


def test_a_board_moves_the_columns_of_both_berths_it_names():
    """Examines the board and hand columns carried by each berth of a meeting."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 near-3 9 4",
    ])
    assert berth_board_count(berth_entry(text, "far-1")) == 1
    assert berth_hand_count(berth_entry(text, "far-1")) == 9
    assert berth_board_count(berth_entry(text, "near-3")) == 1
    assert berth_hand_count(berth_entry(text, "near-3")) == 4


def test_a_board_of_level_hands_falls_by_the_opening_seeds():
    """Examines which house takes a board neither side led on hands."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 near-3 5 5",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert opening_seed(tarrant) > opening_seed(sallow)
    assert (wins_held(tarrant), losses_held(tarrant)) == (1, 0)
    assert (wins_held(sallow), losses_held(sallow)) == (0, 1)
    assert (hands_taken(sallow), hands_given(sallow)) == (5, 5)


def test_a_board_where_neither_side_took_a_hand_is_still_weighed():
    """Examines a meeting at which no hand at all was taken by either house."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 near-3 0 0",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert (wins_held(tarrant), losses_held(tarrant), meetings_held(tarrant)) == (1, 0, 1)
    assert (wins_held(sallow), losses_held(sallow), meetings_held(sallow)) == (0, 1, 1)
    assert (hands_taken(tarrant), hands_given(tarrant)) == (0, 0)
    assert berth_board_count(berth_entry(text, "far-1")) == 1
    assert berth_hand_count(berth_entry(text, "far-1")) == 0
    assert head_tally_of(text, "boards") == 1


def test_a_board_reaching_an_empty_berth_enters_nothing():
    """Examines a meeting called at a berth no house is sitting in."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "board far-1 near-3 9 4",
    ])
    sallow = house_entry(text, "sallow")
    assert (wins_held(sallow), losses_held(sallow), meetings_held(sallow)) == (0, 0, 0)
    assert (hands_taken(sallow), hands_given(sallow)) == (0, 0)
    assert berth_board_count(berth_entry(text, "far-1")) == 0
    assert settled_token(berth_entry(text, "near-3")) == "dark.named"
    assert head_tally_of(text, "boards") == 0


def test_a_bye_carries_no_argument_and_the_field_places_it():
    """Examines which seated house a free win falls to when none is named."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "bye",
    ])
    assert wins_held(house_entry(text, "quinnel")) == 1
    assert wins_held(house_entry(text, "sallow")) == 0
    assert wins_held(house_entry(text, "tarrant")) == 0
    assert settled_state(berth_entry(text, "near-1")) == "RESTED"


def test_a_bye_where_no_house_is_seated_reaches_nothing():
    """Examines a free win called over a bracket holding no house at all."""
    text = replanted_crown(OTHER_CROWN, ["bye", "bye"])
    assert head_tally_of(text, "byes") == 0
    assert tally_counts(text, "houses")["SEATED"] == 8
    assert tally_counts(text, "berths")["DARK"] == 8


def test_a_struck_house_leaves_every_board_it_played_standing():
    """Examines what survives on other houses when one comes off the roll."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "board far-1 near-3 4 9",
        "board near-1 near-3 4 9",
        "strike tarrant",
    ])
    sallow = house_entry(text, "sallow")
    quinnel = house_entry(text, "quinnel")
    tarrant = house_entry(text, "tarrant")
    assert settled_state(tarrant) == "BARRED"
    assert wins_held(tarrant) == 2
    assert (wins_held(sallow), losses_held(sallow), meetings_held(sallow)) == (0, 1, 1)
    assert strength_held(sallow) == 2
    assert strength_held(quinnel) == 2


def test_a_close_ranks_every_house_still_sitting_in_a_berth():
    """Examines the order a close reads over the whole seated field."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "seat rensham mid-2",
        "close",
    ])
    assert sitting_house(berth_entry(text, "mid-2")) == "tarrant"
    assert sitting_house(berth_entry(text, "far-1")) == "rensham"
    assert sitting_house(berth_entry(text, "near-3")) == "sallow"
    assert sitting_house(berth_entry(text, "mid-1")) == "quinnel"


def test_a_close_puts_out_the_houses_ranked_below_the_width():
    """Examines who leaves when the field is larger than the next round allows."""
    text = replanted_crown(OTHER_CROWN, [
        "seat olney mid-1",
        "seat pardle far-3",
        "seat quinnel near-1",
        "seat rensham mid-2",
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat umber mid-3",
        "close",
    ])
    assert settled_state(house_entry(text, "quinnel")) == "CUT"
    assert settled_token(house_entry(text, "quinnel")) == "cut.idle"
    assert settled_state(house_entry(text, "umber")) == "CUT"
    assert tally_counts(text, "houses")["CUT"] == 2
    assert tally_counts(text, "houses")["SEATED"] == 6


def test_a_house_beaten_in_the_round_just_closed_leaves_felled():
    """Examines the ruling on a house that lost a board and then went out."""
    text = settled_bracket(FIRST_CROWN)
    lowen = house_entry(text, "lowen")
    hurst = house_entry(text, "hurst")
    assert settled_state(lowen) == "FELLED"
    assert settled_token(lowen) == "felled.board"
    assert settled_state(hurst) == "FELLED"
    assert settled_token(hurst) == "felled.given"


def test_a_house_unbeaten_in_the_round_just_closed_leaves_cut():
    """Examines the ruling on a house that won its last board and still went out."""
    text = settled_bracket(FIRST_CROWN)
    gorrel = house_entry(text, "gorrel")
    assert settled_state(gorrel) == "CUT"
    assert settled_token(gorrel) == "cut.width"
    assert losses_held(gorrel) == 3


def test_the_marks_a_round_leaves_do_not_reach_the_next_close():
    """Examines whether losses from earlier rounds still weigh at a later close."""
    text = settled_bracket(FIRST_CROWN)
    gorrel = house_entry(text, "gorrel")
    hurst = house_entry(text, "hurst")
    assert losses_held(gorrel) == losses_held(hurst) == 3
    assert settled_state(gorrel) == "CUT"
    assert settled_state(hurst) == "FELLED"


def test_the_reseat_fills_the_berths_the_bracket_names_first():
    """Examines which berths the survivors of a close are put into."""
    order = column_one_of(OTHER_CROWN, "bracket.table")
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "seat rensham mid-2",
        "close",
    ])
    held = [sitting_house(berth_entry(text, name)) for name in order]
    assert held[:4] == ["tarrant", "rensham", "sallow", "quinnel"]
    assert held[4:] == ["-", "-", "-", "-"]


def test_the_reseat_empties_every_berth_beyond_the_width():
    """Examines the berths left holding nobody once a close has moved the field."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "seat rensham mid-2",
        "close",
    ])
    assert settled_state(berth_entry(text, "near-1")) == "VACATED"
    assert settled_token(berth_entry(text, "near-1")) == "void.reseated"
    assert settled_state(berth_entry(text, "near-2")) == "DARK"


def test_the_last_house_left_alone_at_a_close_takes_the_crown():
    """Examines what happens at a close that leaves one house sitting."""
    text = replanted_crown(OTHER_CROWN, ["seat sallow far-1", "close"])
    sallow = house_entry(text, "sallow")
    assert settled_state(sallow) == "CROWNED"
    assert settled_token(sallow) == "crown.sole"
    assert place_held(sallow) == 1
    assert place_rule(sallow) == "place.crown"
    assert settled_state(berth_entry(text, "mid-2")) == "CROWNED"
    assert settled_token(berth_entry(text, "mid-2")) == "held.own"
    assert settled_token(berth_entry(settled_bracket(OTHER_CROWN), "mid-2")) == "held.own"


def test_the_crown_token_reads_the_close_that_gave_it():
    """Examines how the two crowning rules are told apart at the same berth."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "close",
        "close",
        "close",
        "close",
    ])
    tarrant = house_entry(text, "tarrant")
    sallow = house_entry(text, "sallow")
    assert settled_state(tarrant) == "CROWNED"
    assert settled_token(tarrant) == "crown.width"
    assert settled_state(sallow) == "CUT"
    assert settled_token(sallow) == "cut.idle"


def test_a_close_over_an_empty_bracket_still_opens_a_round():
    """Examines a close called when no house is sitting anywhere."""
    text = replanted_crown(OTHER_CROWN, ["close", "close"])
    assert head_tally_of(text, "rounds") == 3
    assert tally_counts(text, "berths")["DARK"] == 8
    assert tally_counts(text, "houses")["SEATED"] == 8
    assert tally_counts(text, "houses")["CROWNED"] == 0


def test_the_crowned_house_takes_the_first_place_outright():
    """Examines the place given to the house that took the crown."""
    for root, name in ((FIRST_CROWN, "birling"), (OTHER_CROWN, "rensham")):
        row = house_entry(settled_bracket(root), name)
        assert place_held(row) == 1
        assert place_rule(row) == "place.crown"


def test_a_house_gone_early_can_place_above_one_gone_later():
    """Examines whether the moment a house stopped decides where it places."""
    text = settled_bracket(FIRST_CROWN)
    ingle = house_entry(text, "ingle")
    hurst = house_entry(text, "hurst")
    lowen = house_entry(text, "lowen")
    assert settled_state(ingle) == "BARRED"
    assert place_held(ingle) < place_held(hurst)
    assert place_held(lowen) < place_held(ingle)
    assert place_held(house_entry(text, "corvane")) < place_held(house_entry(text, "durrow"))


def test_a_place_told_apart_at_the_wins_rung():
    """Examines the naming of a place gap opened by the first rung."""
    text = settled_bracket(OTHER_CROWN)
    pardle = house_entry(text, "pardle")
    olney = house_entry(text, "olney")
    assert place_held(olney) == place_held(pardle) + 1
    assert place_rule(olney) == "place.wins"


def test_a_place_told_apart_at_the_losses_rung():
    """Examines the naming of a place gap that the first rung left level."""
    text = settled_bracket(OTHER_CROWN)
    olney = house_entry(text, "olney")
    quinnel = house_entry(text, "quinnel")
    assert place_held(quinnel) == place_held(olney) + 1
    assert place_rule(quinnel) == "place.losses"


def test_a_place_told_apart_at_the_strength_rung():
    """Examines the naming of a place gap the first two rungs left level."""
    text = settled_bracket(FIRST_CROWN)
    gorrel = house_entry(text, "gorrel")
    assert place_held(gorrel) == 2
    assert place_rule(gorrel) == "place.strength"


def test_a_place_told_apart_at_the_seed_rung():
    """Examines the naming of a place gap that only the seeds could open."""
    text = settled_bracket(OTHER_CROWN)
    umber = house_entry(text, "umber")
    vessen = house_entry(text, "vessen")
    assert place_held(umber) == place_held(vessen) + 1
    assert place_rule(umber) == "place.seed"


def test_a_crowned_berth_outranks_the_bye_it_also_drew():
    """Examines a berth that fits the crowning rung and a lower one at once."""
    plain = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "bye",
    ])
    assert settled_state(berth_entry(plain, "far-1")) == "RESTED"
    text = settled_bracket(FIRST_CROWN)
    assert settled_state(berth_entry(text, "south-2")) == "CROWNED"
    assert settled_token(berth_entry(text, "south-2")) == "held.long"


def test_an_upset_berth_outranks_the_bye_it_also_drew():
    """Examines a berth that both hosted a win from below and drew a free win."""
    text = settled_bracket(FIRST_CROWN)
    assert settled_state(berth_entry(text, "south-1")) == "UPSET"
    assert settled_state(berth_entry(text, "west-1")) == "RESTED"
    assert settled_state(berth_entry(text, "east-3")) == "UPSET"


def test_a_rested_berth_outranks_the_house_that_left_it():
    """Examines a berth that drew a free win and was later emptied."""
    text = settled_bracket(FIRST_CROWN)
    west = berth_entry(text, "west-1")
    assert settled_state(west) == "RESTED"
    assert settled_token(west) == "rest.clear"
    assert sitting_house(west) == "-"


def test_a_berth_that_emptied_reads_below_the_three_rungs_above_it():
    """Examines a berth that held houses, hosted nothing special, and ended empty."""
    text = settled_bracket(FIRST_CROWN)
    east = berth_entry(text, "east-2")
    assert settled_state(east) == "VACATED"
    assert settled_token(east) == "void.reseated"
    assert berth_board_count(east) == 1
    other = settled_bracket(OTHER_CROWN)
    assert settled_token(berth_entry(other, "far-1")) == "void.barred"
    assert settled_token(berth_entry(other, "far-3")) == "void.felled"
    assert settled_token(berth_entry(other, "near-3")) == "void.cut"


def test_a_berth_no_house_ever_took_reads_the_last_rung():
    """Examines the ruling on a berth that never held anybody."""
    text = settled_bracket(FIRST_CROWN)
    north = berth_entry(text, "north-2")
    assert settled_state(north) == "DARK"
    assert settled_token(north) == "dark.silent"
    assert berth_board_count(north) == 0
    assert berth_hand_count(north) == 0


def test_the_crowned_house_outranks_the_berth_it_still_holds():
    """Examines a house that both took the crown and is still sitting down."""
    text = settled_bracket(FIRST_CROWN)
    birling = house_entry(text, "birling")
    assert settled_state(birling) == "CROWNED"
    assert berth_held(birling) == "south-2"
    assert tally_counts(text, "houses")["SEATED"] == 1


def test_a_struck_house_outranks_the_close_that_followed_it():
    """Examines a house coming off the roll just before a close would have moved it."""
    text = settled_bracket(OTHER_CROWN)
    pardle = house_entry(text, "pardle")
    assert settled_state(pardle) == "BARRED"
    assert settled_token(pardle) == "barred.seated"
    without = replanted_crown(OTHER_CROWN, [
        line for line in steps_recorded(OTHER_CROWN) if line != "strike pardle"
    ])
    assert settled_state(house_entry(without, "pardle")) == "FELLED"


def test_a_house_put_out_never_reads_as_one_left_standing():
    """Examines two houses holding no berth, one of them stopped and one not."""
    text = settled_bracket(FIRST_CROWN)
    fenwick = house_entry(text, "fenwick")
    elsham = house_entry(text, "elsham")
    assert berth_held(fenwick) == berth_held(elsham) == "-"
    assert settled_state(fenwick) == "CUT"
    assert settled_state(elsham) == "SEATED"
    assert settled_token(elsham) == "stand.unseated"


def test_the_two_leaving_rules_part_on_the_round_just_closed():
    """Examines the single question that tells the two ways of going out apart."""
    text = settled_bracket(FIRST_CROWN)
    gorrel = house_entry(text, "gorrel")
    lowen = house_entry(text, "lowen")
    assert losses_held(gorrel) == losses_held(lowen) == 3
    assert settled_token(gorrel) == "cut.width"
    assert settled_token(lowen) == "felled.board"


def test_the_two_widths_of_a_win_from_below_part_on_the_gap():
    """Examines how far below the beaten house the winner stood."""
    text = settled_bracket(FIRST_CROWN)
    assert settled_token(berth_entry(text, "north-1")) == "upset.close"
    assert settled_token(berth_entry(text, "east-3")) == "upset.wide"
    close = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 near-3 9 4",
    ])
    assert settled_token(berth_entry(close, "far-1")) == "upset.close"


def test_the_two_free_win_rules_part_at_the_seed_rung():
    """Examines whether the seeds alone separated the lowest house from the next."""
    assert settled_token(berth_entry(settled_bracket(OTHER_CROWN), "near-1")) == "rest.tie"
    assert settled_token(berth_entry(settled_bracket(FIRST_CROWN), "west-1")) == "rest.clear"
    tied = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "seat quinnel near-1",
        "bye",
    ])
    assert settled_token(berth_entry(tied, "near-1")) == "rest.tie"


def test_the_two_crowning_rules_part_on_who_else_left():
    """Examines whether the crowning close also sent anybody home."""
    assert settled_token(house_entry(settled_bracket(FIRST_CROWN), "birling")) == "crown.width"
    assert settled_token(house_entry(settled_bracket(OTHER_CROWN), "rensham")) == "crown.sole"


def test_the_two_striking_rules_part_on_holding_a_berth():
    """Examines whether a house coming off the roll was sitting anywhere."""
    text = settled_bracket(OTHER_CROWN)
    assert settled_token(house_entry(text, "pardle")) == "barred.seated"
    assert settled_token(house_entry(text, "umber")) == "barred.aside"
    assert tally_counts(text, "houses")["BARRED"] == 2


def test_a_record_of_no_steps_leaves_every_berth_untouched():
    """Examines the sheet settled over a record carrying nothing at all."""
    text = replanted_crown(FIRST_CROWN, [])
    assert head_tally_of(text, "rounds") == 1
    assert head_tally_of(text, "boards") == 0
    assert tally_counts(text, "berths") == {"CROWNED": 0, "UPSET": 0, "RESTED": 0,
                                        "VACATED": 0, "DARK": 10}
    assert tally_counts(text, "houses")["SEATED"] == 10
    assert place_held(house_entry(text, "lowen")) == 1
    assert place_held(house_entry(text, "arden")) == 10
    assert place_rule(house_entry(text, "lowen")) == "place.seed"


def test_a_step_naming_what_the_tables_do_not_reaches_nothing():
    """Examines steps calling on a berth or a house nowhere in the tables."""
    text = replanted_crown(OTHER_CROWN, [
        "seat wrayling far-1",
        "seat vessen orling",
        "board far-1 near-3 9 1",
    ])
    _lines, berth_rows, house_rows = carve_bracket(text)
    assert len(berth_rows) == 8
    assert len(house_rows) == 8
    assert settled_token(berth_entry(text, "far-1")) == "dark.named"
    assert settled_token(berth_entry(text, "near-3")) == "dark.named"
    assert berth_held(house_entry(text, "vessen")) == "-"
    assert head_tally_of(text, "boards") == 0


def test_a_step_naming_one_berth_twice_reaches_nothing():
    """Examines a meeting and a giving up that both call on a single berth."""
    text = replanted_crown(OTHER_CROWN, [
        "seat sallow far-1",
        "seat tarrant near-3",
        "board far-1 far-1 9 1",
        "concede near-3 near-3",
    ])
    sallow = house_entry(text, "sallow")
    tarrant = house_entry(text, "tarrant")
    assert (wins_held(sallow), losses_held(sallow), meetings_held(sallow)) == (0, 0, 0)
    assert (wins_held(tarrant), losses_held(tarrant), meetings_held(tarrant)) == (0, 0, 0)
    assert berth_board_count(berth_entry(text, "far-1")) == 0
    assert head_tally_of(text, "boards") == 0
    assert head_tally_of(text, "concedes") == 0


def test_a_house_struck_while_holding_no_berth_empties_none():
    """Examines a house coming off the roll from outside the bracket."""
    text = settled_bracket(OTHER_CROWN)
    umber = house_entry(text, "umber")
    assert settled_state(umber) == "BARRED"
    assert settled_token(umber) == "barred.aside"
    assert berth_held(umber) == "-"
    marks = [settled_token(row) for row in carve_bracket(text)[1]]
    assert marks.count("void.barred") == 1


def test_a_close_beyond_the_declared_widths_holds_the_last_one():
    """Examines a close asking for a round the width table never reached."""
    text = replanted_crown(OTHER_CROWN, [
        "seat olney mid-1",
        "seat pardle far-3",
        "seat quinnel near-1",
        "close",
        "seat sallow near-3",
        "seat tarrant mid-1",
        "close",
    ], widths=[6, 2])
    assert tally_counts(text, "houses")["CUT"] == 3
    assert tally_counts(text, "houses")["SEATED"] == 5
    assert sitting_house(berth_entry(text, "mid-2")) == "pardle"
    assert sitting_house(berth_entry(text, "far-1")) == "tarrant"
    assert head_tally_of(text, "rounds") == 3


def test_a_record_stopping_in_mid_round_leaves_houses_sitting():
    """Examines a record whose last round was never brought to a close."""
    text = replanted_crown(OTHER_CROWN, steps_recorded(OTHER_CROWN)[:-1])
    rensham = house_entry(text, "rensham")
    assert settled_state(rensham) == "SEATED"
    assert settled_token(rensham) == "stand.seated"
    assert berth_held(rensham) == "mid-2"
    mid = berth_entry(text, "mid-2")
    assert settled_state(mid) == "VACATED"
    assert settled_token(mid) == "void.standing"
    assert place_held(rensham) == 1
    assert place_rule(rensham) == "place.wins"
    assert tally_counts(text, "houses")["CROWNED"] == 0


def test_the_two_blocks_are_laid_out_in_two_different_orders():
    """Examines the order each of the sheet's two blocks is written in."""
    text = settled_bracket(OTHER_CROWN)
    lines, berth_rows, house_rows = carve_bracket(text)
    printed = [row[0] for row in berth_rows]
    assert printed == sorted(printed)
    assert printed != column_one_of(OTHER_CROWN, "bracket.table")
    assert [row[0] for row in house_rows] == column_one_of(OTHER_CROWN, "roll.table")
    assert lines[1] == BERTH_BLOCK_HEAD
    assert lines[2 + len(berth_rows)] == HOUSE_BLOCK_LINE


def test_both_tallies_carry_every_state_even_at_nothing():
    """Examines whether a state reached by nobody still keeps its column."""
    text = replanted_crown(OTHER_CROWN, [])
    berths = tally_counts(text, "berths")
    houses = tally_counts(text, "houses")
    assert list(berths) == list(BERTH_LADDER)
    assert list(houses) == list(HOUSE_LADDER_ORDER)
    assert sum(berths.values()) == 8
    assert sum(houses.values()) == 8
    assert berths["CROWNED"] == 0


def test_the_sheet_is_closed_by_a_single_newline():
    """Examines how the filed sheet is terminated and spaced."""
    for root in (FIRST_CROWN, OTHER_CROWN):
        text = settled_bracket(root)
        assert text.endswith("\n")
        assert not text.endswith("\n\n")
        assert "" not in text.rstrip("\n").split("\n")
        assert not any(line.endswith(" ") for line in text.split("\n"))


def test_a_clean_run_says_nothing_on_either_stream():
    """Examines what the run writes to the terminal while filing a sheet."""
    done, target, _home = file_one_bracket(FIRST_CROWN)
    assert done.returncode == 0
    assert done.stdout == ""
    assert done.stderr == ""
    assert target.exists()
    assert Path(BRACKET_TOOL_SRC).is_dir()


def steps_recorded(root):
    steps = []
    path = Path(root) / "record" / "crown.log"
    for raw in path.read_text(encoding="ascii").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            steps.append(" ".join(line.split()[1:]))
    return steps
