"""Verifier suite for ochre-panel-lamp-dispatch (NOC Perl panel dispatcher)."""

from __future__ import annotations

import shutil

import pytest
from conftest import (
    APP,
    BEACON,
    FOLD,
    NOTES,
    OUT,
    PANEL,
    assert_failure,
    assert_success,
    notes_extras,
    out_extras,
    panel_digests,
    run_dispatch,
    sha256_file,
    stage_case,
)
from panel_ref import parse_fixed, read_tsv, width_map

pytestmark = pytest.mark.usefixtures("clean_out")


def _widths():
    cols, _hop, _waiver, _hold, _depth = width_map(read_tsv(PANEL / "widths.tsv"))
    return cols


def test_amber_hall_beacon_rows_match_expected_dispatch():
    """Main amber_hall fixture: beacon rows match flap aging and bell choice."""
    beacon, _ = assert_success("amber_hall")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[0][0] == "LAMP"
    body = {r[0]: r for r in rows[1:]}
    assert body["L1"][3] == "20"  # 120-100
    assert body["L1"][4] == "KLING"
    assert body["L3"][5] == "MASKED"
    assert body["L3"][6] == "*door ajar"


def test_runner_fold_rows_match_shortest_routes():
    """Main fixture runner paths and travel minutes match shortest routes."""
    _, fold = assert_success("amber_hall")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    by_lamp = {r[1]: r for r in rows[1:]}
    assert by_lamp["L1"][0] == "R1"
    assert by_lamp["L1"][2] == "NOC>HALL-A>WING-B>CELL-3"
    assert by_lamp["L1"][3] == "9"
    assert by_lamp["L2"][2] == "NOC>WING-C>CELL-7"


def test_beacon_queue_header_widths_and_lf():
    """beacon.queue header text, fixed widths, LF endings, final newline."""
    assert_success("amber_hall")
    raw = BEACON.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    w = _widths()
    header = raw.split(b"\n", 1)[0].decode()
    assert len(header) == sum(
        w[k]
        for k in [
            "beacon_lamp",
            "beacon_color",
            "beacon_zone",
            "beacon_age",
            "beacon_bell",
            "beacon_blackout",
            "beacon_message",
        ]
    )
    assert header.startswith("LAMP")


def test_runner_fold_header_widths_and_lf():
    """runner.fold header and line formatting with LF endings."""
    assert_success("amber_hall")
    raw = FOLD.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    w = _widths()
    header = raw.split(b"\n", 1)[0].decode()
    assert len(header) == sum(
        w[k]
        for k in [
            "runner_id",
            "runner_lamp",
            "runner_path",
            "runner_travel",
            "runner_handoff",
            "runner_note",
        ]
    )
    assert header.startswith("RUNNER")


def test_duplicate_flaps_collapse_by_lamp_and_text():
    """Repeated flaps for same lamp+text collapse with correct age span."""
    beacon, _ = assert_success("duplicate_flaps")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = [r for r in rows[1:] if r[0]]
    assert len(body) == 1
    assert body[0][0] == "L1"
    assert body[0][3] == "20"  # earliest first=100
    assert body[0][6] == "power drop"


def test_acknowledgement_grace_delays_escalation():
    """Acknowledged flap stays on calmest color bell during grace."""
    beacon, _ = assert_success("grace_ack_delay")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    # grace uses calmest amber bell -> SOFT (priority 1), not LOUD
    assert rows[1][4] == "SOFT"


def test_expired_acknowledgement_escalates_again():
    """Grace expiry restores severity escalation to louder bell."""
    beacon, _ = assert_success("expired_ack")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"


def test_blackout_inherited_from_parent_zone():
    """Ancestor mask prints MASKED but does not star MESSAGE or MASK-HOLD."""
    beacon, fold = assert_success("inherited_blackout")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][5] == "MASKED"
    assert rows[1][2] == "Z-A"
    assert rows[1][6] == "power drop"  # inherited mask: no asterisk
    frows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert frows[1][5] == "DELIVER"


def test_local_blackout_overrides_runner_slip_note():
    """Local zone mask sets runner slip note to MASK-HOLD."""
    _, fold = assert_success("local_blackout")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert rows[1][5] == "MASK-HOLD"


def test_runner_corridor_prefers_shortest_minutes():
    """Graph routing chooses the minimum travel-minute corridor set."""
    _, fold = assert_success("runner_corridor_choice")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert rows[1][0] == "R1"
    assert rows[1][3] == "9"


def test_runner_tie_uses_runner_id_then_path():
    """Equal travel and hop count break ties by runner id then path text."""
    _, fold = assert_success("runner_tie")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert rows[1][0] == "R1"
    assert rows[1][2] == "NOC>ALT>CELL-3"


def test_runner_prefers_fewer_hops_before_runner_id():
    """Equal travel: fewer path hops beat a lexicographically smaller runner_id."""
    _, fold = assert_success("runner_hop_prefers_fewer")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert rows[1][0] == "R2"
    assert rows[1][2] == "NOC>CELL-3"


def test_calm_bell_preference_uses_lowest_priority():
    """During grace the calmest matching color bell wins."""
    beacon, _ = assert_success("calm_bell_preference")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "SOFT"


def test_bell_tie_rule_prints_declared_resolution():
    """Declared tie rule appears in the beacon message marker."""
    beacon, _ = assert_success("bell_tie_with_rule")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "CLANG"  # lex smaller than KLING
    assert "[tie:lex-bell]" in rows[1][6]


def test_widths_reject_too_long_message():
    """Oversized rendered message field makes the board unsafe."""
    assert_failure("narrow_widths")


def test_shuffled_panel_files_keep_product_hashes():
    """Reordered flap/lamp/route/bell rows preserve product hashes."""
    assert_success("amber_hall")
    h1 = (sha256_file(BEACON), sha256_file(FOLD))
    assert_success("shuffled_panel")
    h2 = (sha256_file(BEACON), sha256_file(FOLD))
    assert h1 == h2


def test_second_dispatch_run_is_byte_identical():
    """Sound board run twice yields identical artifact bytes."""
    assert_success("amber_hall")
    b1, f1 = BEACON.read_bytes(), FOLD.read_bytes()
    proc = run_dispatch()
    assert proc.returncode == 0
    assert BEACON.read_bytes() == b1
    assert FOLD.read_bytes() == f1


def test_panel_inputs_remain_unchanged():
    """Hashes of /app/panel stay identical across a sound dispatch."""
    stage_case("amber_hall")
    before = panel_digests()
    proc = run_dispatch()
    assert proc.returncode == 0
    assert panel_digests() == before


def test_clock_disagreement_leaves_output_empty():
    """Mismatched clock ids prevent publication."""
    assert_failure("clock_disagreement")


def test_overlapping_rack_zones_leave_output_empty():
    """Intersecting zone ranges are unsafe."""
    assert_failure("overlapping_zones")


def test_unknown_lamp_reference_leaves_output_empty():
    """Flap pointing to no lamp clears products."""
    assert_failure("unknown_lamp")


def test_missing_blackout_parent_leaves_output_empty():
    """Broken blackout inheritance chain is unsafe."""
    assert_failure("missing_blackout_parent")


def test_early_acknowledgement_leaves_output_empty():
    """Acknowledgement before flap first minute prevents output."""
    assert_failure("early_acknowledgement")


def test_corridor_dead_end_leaves_output_empty():
    """Required runner without reachable route clears products."""
    assert_failure("corridor_dead_end")


def test_negative_travel_minutes_leave_output_empty():
    """Negative corridor duration is rejected."""
    assert_failure("negative_travel")


def test_bell_tie_without_rule_leaves_output_empty():
    """Equal bell priority with no printed rule clears products."""
    assert_failure("bell_tie_without_rule")


def test_impossible_width_leaves_output_empty():
    """Nonpositive width values prevent rendering."""
    assert_failure("impossible_width")


def test_stale_products_removed_after_unsafe_board():
    """Good products vanish after an unsafe case is dispatched."""
    assert_success("amber_hall")
    assert BEACON.exists() and FOLD.exists()
    assert_failure("clock_disagreement", stale=False)
    assert not BEACON.exists() and not FOLD.exists()


def test_forced_perl_failure_leaves_output_empty():
    """Simulated nonzero Perl run leaves no partial product files."""
    assert_failure("forced_perl_failure")


def test_notes_directory_returns_to_placeholder():
    """Scratch notes are removed after sound and unsafe runs."""
    assert_success("amber_hall")
    assert notes_extras() == []
    assert_failure("unknown_lamp")
    assert notes_extras() == []
    assert (NOTES / ".keep").exists()


def test_no_unlisted_products_are_written():
    """Output directory contains only allowed product names."""
    assert_success("amber_hall")
    names = sorted(p.name for p in OUT.iterdir())
    assert names == [".keep", "beacon.queue", "runner.fold"]
    assert (OUT / ".keep").exists()


def test_blackout_group_suppresses_duplicate_beacons():
    """Multiple lamps in a silence group with a mask keep one MASKED queue row."""
    beacon, _ = assert_success("silence_group")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = [r for r in rows[1:] if r[0]]
    assert len(body) == 1
    assert body[0][0] == "L1"
    assert body[0][5] == "MASKED"
    assert body[0][6].startswith("*")


def test_silence_keeps_masked_not_lexicographic_clear():
    """CLEAR lamp with smaller id is dropped; smallest MASKED id is kept."""
    beacon, _ = assert_success("silence_clear_sorts_first")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = [r for r in rows[1:] if r[0]]
    assert len(body) == 1
    assert body[0][0] == "L2"
    assert body[0][5] == "MASKED"
    assert body[0][6] == "*fan stall"


def test_grace_window_excludes_upper_bound():
    """At panel_minute == ack+grace, half-open grace has ended and severity escalates."""
    beacon, _ = assert_success("grace_boundary_exclusive")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"


def test_zero_grace_minutes_never_suppresses():
    """grace_minutes=0 yields an empty window; escalated bell is used."""
    beacon, _ = assert_success("zero_grace")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"


def test_collapse_same_first_minute_uses_lex_flap_id():
    """Equal first_minute picks lex-smaller flap_id severity, not the louder one."""
    beacon, _ = assert_success("collapse_same_first_minute")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "CHIME"  # MED from F1, not LOUD from F2


def test_runner_handoff_sorted_numerically_not_lexicographically():
    """Handoff 99 precedes 100 under numeric sort (lexicographic string sort inverts)."""
    _, fold = assert_success("handoff_numeric_sort")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    handoffs = [r[4] for r in rows]
    assert handoffs == ["99", "100"]
    assert [r[1] for r in rows] == ["L8", "L9"]


def test_blackout_parent_cycle_leaves_output_empty():
    """Parent-chain cycle in blackouts.tsv is unsafe."""
    assert_failure("blackout_cycle")


def test_unknown_acknowledgement_flap_leaves_output_empty():
    """Acknowledgement naming a flap id absent from flaps.tsv is unsafe."""
    assert_failure("unknown_ack")


def test_reversed_flap_window_leaves_output_empty():
    """Raw flap rows with last_minute before first_minute are unsafe."""
    assert_failure("reversed_flap_window")


def test_tie_marker_can_overflow_message_width():
    """Raw text may fit; appending [tie:…] can still overflow beacon_message."""
    assert_failure("tie_marker_width_overflow")


def test_grace_color_bell_tie_appends_marker():
    """Grace-time color-wide priority ties still require tie_rule and marker."""
    beacon, _ = assert_success("grace_color_bell_tie")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "HUSH"  # lex smaller than SOFT at priority 1
    assert "[tie:grace-lex]" in rows[1][6]


def test_ack_on_non_primary_collapsed_flap_uses_collapsed_first():
    """Ack on a secondary contributor is early-checked against collapsed first_minute."""
    beacon, _ = assert_success("ack_on_secondary_flap")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "SOFT"  # in grace via secondary flap ack


def test_nonbinary_blackout_mask_leaves_output_empty():
    """masked values other than 0 or 1 make the board unsafe."""
    assert_failure("bad_mask_value")


def test_severity_promotion_picks_max_threshold_once():
    """Non-grace promotion chooses largest matching age_threshold, no chaining."""
    beacon, _ = assert_success("severity_promotion")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"  # promoted LOW→HIGH


def test_severity_promotion_skipped_during_grace():
    """Grace suppresses promotion; calm color bell is used instead."""
    beacon, _ = assert_success("promotion_skipped_in_grace")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "SOFT"


def test_severity_promotion_does_not_chain():
    """After one promotion MED→HIGH, a HIGH→LOW rule must not apply."""
    beacon, _ = assert_success("promotion_no_chain")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"


def test_negative_hop_penalty_leaves_output_empty():
    """Negative hop_penalty in widths.tsv is unsafe."""
    assert_failure("negative_hop_penalty")


def test_beacon_rows_sorted_by_age_descending():
    """Beacon rows use numeric age descending, then lamp_id."""
    beacon, _ = assert_success("amber_hall")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )[1:]
    ages = [int(r[3]) for r in rows]
    assert ages == sorted(ages, reverse=True)
    assert [r[0] for r in rows] == ["L3", "L1", "L2"]


def test_runner_slips_keep_handoff_minutes_sorted():
    """Runner product rows order by handoff minute and route tie keys."""
    _, fold = assert_success("amber_hall")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    handoffs = [int(r[4]) for r in rows]
    assert handoffs == sorted(handoffs)


def test_beacon_age_uses_first_flap_minute():
    """Age is based on earliest collapsed flap minute."""
    beacon, _ = assert_success("duplicate_flaps")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][3] == "20"


def test_last_seen_minute_keeps_recent_alarm_active():
    """Collapsed last_minute extends the half-open active window past earlier ends."""
    # duplicate_flaps collapses last to 140; still active at panel 120 (not at last_minute)
    beacon, _ = assert_success("duplicate_flaps")
    assert "power drop" in beacon


def test_zone_boundary_values_are_inclusive():
    """Lamps exactly on zone limits resolve to that zone."""
    beacon, _ = assert_success("zone_boundary")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    by_lamp = {r[0]: r for r in rows[1:]}
    assert by_lamp["L1"][2] == "Z-A"
    assert by_lamp["L2"][2] == "Z-A"  # rack 30 is Z-A hi


def test_empty_active_board_still_writes_headers():
    """Valid board with no active flaps writes header-only products."""
    beacon, fold = assert_success("empty_active")
    assert beacon.count("\n") == 1
    assert fold.count("\n") == 1
    assert beacon.startswith("LAMP")
    assert fold.startswith("RUNNER")


def test_queue_and_fold_lamp_sets_agree():
    """Cross-check lamp ids between beacon and runner products."""
    beacon, fold = assert_success("amber_hall")
    w = _widths()
    brows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )[1:]
    rrows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert {r[0] for r in brows} == {r[1] for r in rrows}


def test_output_paths_cannot_escape_out_area():
    """Hostile OUT setting still creates only permitted product paths."""
    stage_case("amber_hall")
    hostile = APP / "notes" / "escape_out"
    if hostile.exists():
        shutil.rmtree(hostile)
    proc = run_dispatch(out=hostile)
    assert proc.returncode != 0
    assert not (hostile / "beacon.queue").exists()
    assert not (hostile / "runner.fold").exists()
    # legitimate out still empty / unchanged-safe
    assert notes_extras() == [] or all(p.name == "escape_out" for p in notes_extras())
    # clean any dir created before rejection
    if hostile.exists():
        shutil.rmtree(hostile)
    for p in notes_extras():
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)


def test_masked_message_uses_asterisk_prefix():
    """Local mask prefixes MESSAGE with *; CLEAR lamps stay unstarred."""
    beacon, _ = assert_success("amber_hall")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = {r[0]: r for r in rows[1:]}
    assert body["L1"][6] == "power drop"
    assert body["L3"][6] == "*door ajar"


def test_masked_star_then_tie_marker_order():
    """Asterisk is applied before the [tie:…] suffix with no spaces."""
    beacon, _ = assert_success("masked_star_with_tie")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][5] == "MASKED"
    assert rows[1][6] == "*power drop[tie:lex-bell]"


def test_masked_asterisk_can_overflow_message_width():
    """Fitting raw text still overflows after the MASKED asterisk is prefixed."""
    assert_failure("masked_star_width_overflow")


def test_duplicate_corridor_edges_use_minimum_travel():
    """Parallel identical edges keep the cheapest travel_minutes only."""
    _, fold = assert_success("duplicate_corridor_edge")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert rows[1][0] == "R1"
    assert rows[1][2] == "NOC>MID>CELL-3"
    assert rows[1][3] == "5"


def test_unknown_operator_leaves_output_empty():
    """Ack operator absent from operators.tsv is unsafe."""
    assert_failure("unknown_operator")


def test_duplicate_operator_leaves_output_empty():
    """Duplicate operator_id rows make the board unsafe."""
    assert_failure("duplicate_operator")


def test_last_minute_exclusive_leaves_headers_only():
    """panel_minute == last_minute is inactive under the half-open flap window."""
    beacon, fold = assert_success("last_minute_exclusive")
    assert beacon.count("\n") == 1
    assert fold.count("\n") == 1


def test_hold_surcharge_reorders_runner_fold():
    """BLACKOUT=MASKED hold_surcharge can push a short route after a longer CLEAR."""
    _, fold = assert_success("hold_surcharge_reorders")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L1", "L2"]
    assert rows[0][4] == "124"
    assert rows[1][4] == "132"
    assert rows[1][5] == "MASK-HOLD"


def test_inherited_mask_surcharge_with_deliver_note():
    """Inherited MASKED adds hold_surcharge while NOTE stays DELIVER."""
    _, fold = assert_success("inherited_surcharge_reorders")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L1", "L2"]
    assert rows[1][4] == "132"
    assert rows[1][5] == "DELIVER"


def test_same_age_masked_sorts_before_clear():
    """Equal age: MASKED precedes CLEAR despite a larger lamp_id."""
    beacon, _ = assert_success("same_age_masked_sorts_first")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )[1:]
    assert [r[0] for r in rows if r[0]] == ["L9", "L1"]
    assert rows[0][5] == "MASKED"
    assert rows[1][5] == "CLEAR"


def test_severity_demotion_is_allowed():
    """Promotion may demote loudness; bell follows the quieter severity."""
    beacon, _ = assert_success("severity_demotion")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "SOFT"  # HIGH demoted to LOW


def test_missing_hold_surcharge_leaves_output_empty():
    """widths.tsv without hold_surcharge is unsafe."""
    assert_failure("missing_hold_surcharge")


def test_negative_hold_surcharge_leaves_output_empty():
    """Negative hold_surcharge is unsafe."""
    assert_failure("negative_hold_surcharge")


def test_out_keep_survives_sound_and_unsafe_runs():
    """`/app/out/.keep` remains after sound and unsafe dispatches."""
    assert_success("amber_hall")
    assert (OUT / ".keep").exists()
    assert_failure("clock_disagreement", stale=False)
    assert (OUT / ".keep").exists()


def test_inherited_mask_silence_keeps_unstarred_message():
    """Inherited MASKED does not suppress CLEAR peers; MESSAGE stays unstarred."""
    beacon, fold = assert_success("inherited_silence_no_star")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = {r[0]: r for r in rows[1:] if r[0]}
    assert set(body) == {"L1", "L2"}
    assert body["L1"][5] == "MASKED"
    assert body["L1"][6] == "power drop"
    assert body["L2"][5] == "CLEAR"
    frows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    by_lamp = {r[1]: r for r in frows[1:]}
    assert by_lamp["L1"][5] == "DELIVER"


def test_span_age_drives_promotion_not_board_age():
    """Promotion thresholds use primary span age; board age alone may be too small."""
    beacon, _ = assert_success("span_age_promotes")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][3] == "20"  # board age
    assert rows[1][4] == "LOUD"  # span 30 > 25 promoted LOW→HIGH


def test_primary_span_not_collapsed_max_last():
    """Later contributor extends activity but not promotion span."""
    beacon, _ = assert_success("primary_span_blocks_collapsed_promo")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][3] == "15"  # board age from collapsed first
    assert rows[1][4] == "SOFT"  # primary span 20; not LOUD


def test_promo_threshold_equality_does_not_match():
    """span_age == age_threshold is excluded by strict >."""
    beacon, _ = assert_success("promo_equality_excluded")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "SOFT"


def test_promo_threshold_tie_prefers_quietest():
    """Equal age_threshold → quietest severity_to."""
    beacon, _ = assert_success("promo_tie_prefers_quiet")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "CHIME"  # MED, not LOUD/HIGH


def test_latest_ack_only_controls_grace():
    """Older long grace is ignored when a later short ack is the chosen grace source."""
    beacon, _ = assert_success("latest_ack_overrides_old_grace")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"  # not in grace


def test_silence_prefers_local_masked_over_smaller_inherited():
    """Local MASKED wins silence retention over a smaller inherited-only id."""
    beacon, _ = assert_success("silence_prefers_local_mask")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = [r for r in rows[1:] if r[0]]
    assert len(body) == 1
    assert body[0][0] == "L2"
    assert body[0][6] == "*fan stall"


def test_depth_penalty_reorders_runner_fold():
    """Local masked_depth * depth_penalty can invert handoff order."""
    _, fold = assert_success("depth_penalty_reorders")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L1", "L2"]
    assert rows[0][4] == "124"
    assert rows[1][4] == "132"
    assert rows[1][5] == "MASK-HOLD"


def test_missing_depth_penalty_leaves_output_empty():
    """widths.tsv without depth_penalty makes the board unsafe."""
    assert_failure("missing_depth_penalty")


def test_negative_depth_penalty_leaves_output_empty():
    """Negative depth_penalty in widths.tsv makes the board unsafe."""
    assert_failure("negative_depth_penalty")


def test_grace_waives_hold_surcharge_only():
    """In-grace MASKED omits hold_surcharge and can sort ahead of CLEAR."""
    _, fold = assert_success("grace_waives_hold_only")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L2", "L1"]
    assert rows[0][4] == "123"
    assert rows[1][4] == "126"


def test_grace_still_applies_masked_depth_tax():
    """Grace does not waive masked_depth * depth_penalty."""
    _, fold = assert_success("grace_keeps_depth_tax")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L1", "L2"]
    assert rows[0][4] == "124"
    assert rows[1][4] == "132"


def test_silence_keeps_oldest_local_masked():
    """After local filter, silence keeps max board age among peers."""
    beacon, _ = assert_success("silence_age_among_local")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    body = [r for r in rows[1:] if r[0]]
    assert len(body) == 1
    assert body[0][0] == "L9"
    assert body[0][3] == "30"


def test_masked_depth_counts_masked_zones_only():
    """Unmasked parent links do not inflate masked_depth tax."""
    _, fold = assert_success("masked_depth_ignores_unmasked_links")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L1", "L2"]
    assert rows[1][4] == "132"


def test_secondary_ack_before_own_first_not_in_grace():
    """Secondary ack before its row first_minute is grace-ineligible."""
    beacon, _ = assert_success("secondary_ack_grace_gated")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "LOUD"


def test_secondary_gated_falls_back_to_primary_grace():
    """Gated secondary must not steal grace from an older primary ack."""
    beacon, _ = assert_success("secondary_gated_falls_to_primary")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )
    assert rows[1][4] == "SOFT"


def test_hop_waiver_reorders_runner_fold():
    """billed_hops = max(0, hops - hop_waiver) can invert fold order."""
    _, fold = assert_success("hop_waiver_reorders")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert [r[1] for r in rows] == ["L1", "L2"]
    assert rows[0][4] == "131"
    assert rows[1][4] == "132"


def test_missing_hop_waiver_leaves_output_empty():
    assert_failure("missing_hop_waiver")


def test_negative_hop_waiver_leaves_output_empty():
    assert_failure("negative_hop_waiver")


def test_pre_silence_message_overflow_leaves_output_empty():
    """Width-check runs before silence; suppressed CLEAR overflow still unsafes."""
    assert_failure("pre_silence_width_overflow")


def test_dispatcher_scrubs_stray_out_entries():
    """Dispatcher must remove unauthorized OUT files/dirs, keeping .keep."""
    stage_case("empty_active")
    junk = OUT / "testunsafe"
    junk.mkdir(parents=True, exist_ok=True)
    (junk / "x.txt").write_text("nope\n", encoding="utf-8")
    (OUT / "scratch.tmp").write_text("x\n", encoding="utf-8")
    proc = run_dispatch()
    assert proc.returncode == 0
    assert out_extras() == []
    assert (OUT / ".keep").exists()
    assert BEACON.exists() and FOLD.exists()


def test_inherited_mask_skips_depth_tax():
    """Inherited MASKED does not pay masked_depth * depth_penalty."""
    _, fold = assert_success("inherited_depth_skips_tax")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    by_lamp = {r[1]: r for r in rows}
    assert by_lamp["L2"][4] == "122"
    assert by_lamp["L2"][5] == "DELIVER"
    assert by_lamp["L1"][4] == "126"


def test_handoff_score_beats_shorter_travel_runner():
    """Across runners, eventual handoff can beat raw travel."""
    _, fold = assert_success("handoff_beats_travel_runner")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )
    assert rows[1][0] == "R-long"
    assert rows[1][3] == "2"
    assert rows[1][4] == "122"


def test_travel_beats_intra_runner_hop_tax():
    """Per-runner path picks travel-shortest even when hop tax prefers fewer hops."""
    _, fold = assert_success("travel_beats_intra_runner_hop_tax")
    w = _widths()
    rows = parse_fixed(
        fold,
        [
            w["runner_id"],
            w["runner_lamp"],
            w["runner_path"],
            w["runner_travel"],
            w["runner_handoff"],
            w["runner_note"],
        ],
    )[1:]
    assert len(rows) == 1
    assert rows[0][2] == "NOC>MID>CELL-X"
    assert rows[0][3] == "2"  # TRAVEL is corridor sum, not taxed
    assert rows[0][4] == "222"  # 120 + 2 + 2*50


def test_silence_age_tie_keeps_lex_smallest_lamp():
    """Equal board ages among local MASKED → exactly one survivor, lex-min id."""
    beacon, _ = assert_success("silence_age_tie_lex_lamp")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )[1:]
    body = [r for r in rows if r[0]]
    assert len(body) == 1
    assert body[0][0] == "L1"


def test_beacon_sort_uses_board_age_not_span():
    """Larger span must not outrank a larger board age."""
    beacon, _ = assert_success("beacon_sort_board_not_span")
    w = _widths()
    rows = parse_fixed(
        beacon,
        [
            w["beacon_lamp"],
            w["beacon_color"],
            w["beacon_zone"],
            w["beacon_age"],
            w["beacon_bell"],
            w["beacon_blackout"],
            w["beacon_message"],
        ],
    )[1:]
    body = [r for r in rows if r[0]]
    assert [r[0] for r in body] == ["L2", "L1"]
    assert body[0][3] == "30"
    assert body[1][3] == "20"
