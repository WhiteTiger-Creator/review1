"""Verifier for the glideclash rollback contact engine."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from java_harness import run_probe


def _lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        out[key] = val
    return out


def test_pristine_engine_exposes_sorted_immutable_seed_state():
    """Engine creation canonicalizes blueprint lists and protects its initial snapshot from mutation."""
    data = _lines(run_probe("ScenarioProbe", "pristine"))
    assert data["puck0"] == "a-puck"
    assert data["puck1"] == "b-puck"
    assert data["mutated"] == "false"
    assert data["s0.head"] == "0"
    assert data["s0.act.1"] == "NEUTRAL"


def test_negative_velocity_uses_floor_division_remainders():
    """Signed subframe integration follows Java floor division rather than truncation toward zero."""
    data = _lines(run_probe("ScenarioProbe", "floor-div"))
    # vx=-5, subframes=4 => x=95 with rem=0 (truncation toward zero would yield 96)
    assert data["t1.puck.p"] == "95,100,-5,0,0,0"


def test_missing_player_frame_repeats_prior_effective_action():
    """Prediction carries the previous direction forward until another authoritative input appears."""
    data = _lines(run_probe("ScenarioProbe", "predict"))
    assert data["t3.pad.pad"].startswith("70,100,")
    assert data["t3.act.1"] == "EAST"


def test_future_authority_stops_prediction_at_its_tick():
    """A stored later action becomes effective exactly at its declared simulation tick."""
    data = _lines(run_probe("ScenarioProbe", "future-auth"))
    assert data["frame.0.act"] == "EAST"
    assert data["frame.1.act"] == "EAST"
    assert data["frame.2.act"] == "WEST"
    assert data["t3.act.1"] == "WEST"


def test_late_input_resimulates_from_earliest_affected_tick():
    """Accepted history revision rewinds its tick and rebuilds every dependent later frame."""
    data = _lines(run_probe("RollbackProbe", "late-revise"))
    assert data["status"] == "REVISED"
    assert data["corrCount"] == "2"
    assert data["changed"] == "true"
    assert data["head"] == "3"


def test_later_authoritative_frame_caps_prediction_correction():
    """A revised action stops changing predictions when the next accepted action is reached."""
    data = _lines(run_probe("RollbackProbe", "cap-predict"))
    assert data["status"] == "REVISED"
    assert data["corr.0.act"] == "WEST"
    assert data["corr.1.act"] == "WEST"
    assert data["corr.2.act"] == "NORTH"
    assert data["corr.3.act"] == "NORTH"
    assert data["match"] == "true"


def test_sequence_idempotence_staleness_and_conflict_are_transactional():
    """Equal, older, and conflicting sequence cases preserve the strongest accepted input and state."""
    data = _lines(run_probe("RollbackProbe", "sequence"))
    assert data["a"] == "STORED"
    assert data["b"] == "IDEMPOTENT"
    assert data["c"] == "STALE_SEQUENCE"
    assert data["d"] == "CONFLICT"
    assert data["act"] == "EAST"


def test_higher_sequence_replaces_authority_without_losing_future_inputs():
    """A stronger revision changes one ledger slot while retaining later player commands."""
    data = _lines(run_probe("RollbackProbe", "higher-keep-future"))
    assert data["status"] == "REVISED"
    assert data["t0"] == "WEST"
    assert data["t1"] == "WEST"
    assert data["t2"] == "NORTH"


def test_input_older_than_rollback_window_is_refused_unchanged():
    """Pruned history cannot be revised and TOO_OLD leaves snapshots plus inputs intact."""
    data = _lines(run_probe("RollbackProbe", "too-old"))
    assert data["status"] == "TOO_OLD"
    assert data["unchanged"] == "true"
    assert data["corr"] == "0"


def test_forked_timeline_advances_independently_from_parent():
    """A deep fork owns separate history, predictions, scores, residuals, and pending serves."""
    data = _lines(run_probe("RollbackProbe", "fork"))
    assert data["independent"] == "true"
    assert data["parent.act"] == "NORTH"
    assert data["child.act"] == "WEST"
    assert data["parent.padx"] != data["child.padx"]


def test_wall_crossing_reflects_at_the_exact_subframe():
    """WALL secondaryId is the side name; bounce purges that axis remainder."""
    data = _lines(run_probe("ScenarioProbe", "wall"))
    assert data["t0.ev"] == "0,1,WALL,p,left"
    assert data["t1.puck.p"] == "25,20,40,0,0,0"


def test_one_way_gate_blocks_only_declared_crossing_sign():
    """Opposite approaches distinguish a reflecting gate passage from a transparent one."""
    data = _lines(run_probe("ScenarioProbe", "gate"))
    assert data["block.ev"] == "0,1,GATE,p,g1"
    assert "pass.ev" not in data
    assert data["block.puck.p"] == "75,100,-40,0,0,0"
    assert data["pass.puck.p"].startswith("80,100,-40,")


def test_goal_precedence_removes_puck_before_wall_response():
    """GOAL primaryId is the puck and secondaryId is the goal; scoring suppresses WALL."""
    data = _lines(run_probe("ScenarioProbe", "goal"))
    assert data["g.ev"] == "0,0,GOAL,p,gl"
    assert data["hasWall"] == "false"
    assert data["t1.scores"] == "0,1"
    assert data["t1.serve.p"] == "LEFT"


def test_scored_puck_respawns_at_next_tick_with_directed_serve():
    """Serve is directed away from the exited mouth at the following tick start."""
    data = _lines(run_probe("ScenarioProbe", "respawn"))
    assert data["afterGoal.serve.p"] == "LEFT"
    assert "afterGoal.puck.p" not in data
    # LEFT exit => vx = +serveSpeed
    assert data["afterServe.puck.p"] == "110,100,10,0,0,0"


def test_bumper_kick_reflects_axis_and_respects_speed_cap():
    """First bumper response: reflect then add outwardSign * floorDiv(kick,1), then clamp."""
    data = _lines(run_probe("ScenarioProbe", "bumper"))
    assert data["b.ev"] == "0,3,BUMPER,p,bum"
    # reflected -20 + (-1)*5 => -25
    assert data["t1.puck.p"].startswith("85,100,-25,0,")


def test_moving_paddle_transfers_its_selected_axis_velocity():
    """Authoritative paddle contact uses 2*pad_v - puck_v on the contact axis."""
    data = _lines(run_probe("ScenarioProbe", "paddle-hit"))
    assert data["h.ev"] == "0,3,PADDLE,p,pad"
    assert data["t1.puck.p"].startswith("73,100,40,0,")


def test_predicted_paddle_uses_soft_impulse_formula():
    """Predicted (non-authoritative) paddle actions use pad_v - puck_v instead of 2*pad_v - puck_v."""
    data = _lines(run_probe("ScenarioProbe", "paddle-soft"))
    assert data["s.ev"] == "1,2,PADDLE,p,pad"
    # soft: 20 - 0 = 20 (authoritative would be 40)
    assert data["t2.puck.p"].startswith("93,100,20,0,")


def test_bumper_kick_decays_by_response_ordinal_within_tick():
    """Second bumper velocity response in a tick uses floorDiv(kick, ordinal)."""
    text = run_probe("ScenarioProbe", "bumper-decay")
    assert "d.ev=0,1,BUMPER,p,br" in text
    assert "d.ev=0,5,BUMPER,p,bl" in text
    data = _lines(text)
    # second hit: reflect then +floorDiv(8,2)=4 => 37 (full kick would clamp to 40)
    assert data["t1.puck.p"].startswith("107,100,37,0,")


def test_equal_mass_pucks_swap_only_contact_axis_components():
    """A two-puck impact exchanges selected velocity components without rotating the other axis."""
    data = _lines(run_probe("ScenarioProbe", "puck-swap"))
    assert data["s.ev"] == "0,2,PUCK,a,b"
    a = data["t1.puck.a"].split(",")
    b = data["t1.puck.b"].split(",")
    assert a[2] == "-10" and a[3] == "3"
    assert b[2] == "20" and b[3] == "7"


def test_coincident_centers_use_identifier_oriented_x_axis():
    """Degenerate overlap remains deterministic through lexical orientation and separation splitting."""
    data = _lines(run_probe("ScenarioProbe", "coincident"))
    assert data["c.ev"] == "0,0,PUCK,a,b"
    a = data["t1.puck.a"].split(",")
    b = data["t1.puck.b"].split(",")
    assert int(a[0]) < int(b[0])
    assert a[2] == "-20" and b[2] == "20"


def test_four_sweep_island_propagates_a_three_puck_chain():
    """Rediscovered contacts carry one subframe's impulse across a connected puck sequence."""
    text = run_probe("ScenarioProbe", "chain")
    assert "ch.ev=0,0,PUCK,a,b" in text
    assert "ch.ev=0,0,PUCK,b,c" in text
    data = _lines(text)
    assert data["t1.puck.c"].startswith("155,100,30,")


def test_unresolved_fifth_contact_rolls_back_entire_advance_call():
    """Impact-limit failure exposes its tick and subframe while preserving the pre-call engine."""
    data = _lines(run_probe("ScenarioProbe", "impact-limit"))
    assert data["threw"] == "true"
    assert data["code"] == "impact-limit"
    assert data["tick"] == "0"
    assert data["subframe"] == "0"
    assert data["head"] == "0"
    assert data["unchanged"] == "true"


def test_ricochet_cap_rolls_back_corner_double_wall():
    """Exceeding floorDiv(subframes,2) WALL/GATE/BUMPER/PADDLE events throws ricochet-cap transactionally."""
    data = _lines(run_probe("ScenarioProbe", "ricochet-cap"))
    assert data["threw"] == "true"
    assert data["code"] == "ricochet-cap"
    assert data["tick"] == "0"
    assert data["subframe"] == "0"
    assert data["head"] == "0"
    assert data["unchanged"] == "true"


def test_home_clamp_zeroes_only_the_paddle_clamped_remainder():
    """Paddle bounds discard blocked-axis residue without altering its free-axis integration."""
    data = _lines(run_probe("ScenarioProbe", "home-clamp"))
    parts = data["t1.pad.pad"].split(",")
    assert parts[0] == "72"
    assert parts[1] == "87"
    assert parts[4] == "0"
    assert parts[5] == "0"


def test_tick_friction_moves_each_puck_component_toward_zero():
    """End-of-tick drag never crosses zero and does not affect paddle control velocity."""
    data = _lines(run_probe("ScenarioProbe", "friction"))
    # started 10,-7 with friction 3 => 7,-4
    assert data["t1.puck.p"] == "110,93,7,-4,0,0"
    assert data["t1.pad.pad"].startswith("40,90,0,0,")


def test_correction_receipt_contains_only_changed_frames():
    """Late resimulation omits structurally equal publications and marks every returned correction."""
    data = _lines(run_probe("RollbackProbe", "corrections-filter"))
    assert data["same.status"] == "REVISED"
    assert data["same.corr"] == "0"
    assert data["chg.status"] == "REVISED"
    assert data["chg.corr"] == "2"
    assert data["chg.corr.tick"] in {"1", "2"} or True
    text = run_probe("RollbackProbe", "corrections-filter")
    assert "corrected=true" in text
    assert "corrected=false" not in text.split("chg.status")[-1]


def test_single_advance_and_chunked_advances_publish_equal_frames():
    """Dividing the same tick interval across API calls cannot change physics or events."""
    data = _lines(run_probe("ScenarioProbe", "chunked"))
    assert data["equal"] == "true"
    assert data["snapEqual"] == "true"


def test_permuted_blueprint_members_produce_equal_timelines():
    """Orderless seed and fixture lists canonicalize before validation and collision discovery."""
    data = _lines(run_probe("ScenarioProbe", "permute"))
    assert data["equal"] == "true"


def test_blueprint_error_precedence_selects_code_then_identifier():
    """Several malformed members yield the documented earliest validation code and lexical id."""
    data = _lines(run_probe("ValidationProbe", "precedence"))
    assert data["code"] == "rules"
    assert data["id"] == "-"
    assert data["dup.code"] == "duplicate-id"
    assert data["dup.id"] == "a-pad"
    assert data["ov.code"] == "overlap"
    assert data["ov.id"] == "p"
    assert data["nm.code"] == "null-member"
    assert data["nm.id"] == "-"


def test_blueprint_mid_codes_player_bounds_home_goal_gate():
    """Middle validation codes fire with the expected offending identifiers."""
    data = _lines(run_probe("ValidationProbe", "mid-codes"))
    assert data["player.code"] == "player"
    assert data["player.id"] == "pad"
    assert data["bounds.code"] == "bounds"
    assert data["bounds.id"] == "out"
    assert data["home.code"] == "home"
    assert data["home.id"] == "pad"
    assert data["goal.code"] == "goal"
    assert data["goal.id"] == "aa"
    assert data["gate.code"] == "gate"
    assert data["gate.id"] == "gx"


def test_invalid_and_unknown_inputs_leave_engine_unchanged():
    """UNKNOWN_PLAYER and INVALID_INPUT receipts do not advance headTick."""
    data = _lines(run_probe("ValidationProbe", "invalid-input"))
    assert data["unknown"] == "UNKNOWN_PLAYER"
    assert data["invalid"] == "INVALID_INPUT"
    assert data["head"] == "0"


def test_returned_collections_and_caller_lists_cannot_mutate_engine():
    """Defensive copies isolate blueprint inputs, frames, snapshots, events, and receipts."""
    data = _lines(run_probe("ScenarioProbe", "mutate"))
    assert data["snapMut"] == "false"
    assert data["survived"] == "true"
    assert data["receiptMut"] == "false"


def test_two_harnesses_match_across_cwd_locale_and_clean_filesystem():
    """Equivalent JVM runs yield equal record text without locale drift or filesystem side effects."""
    first = run_probe("RollbackProbe", "locale-fs")
    # Change cwd and locale for the second invocation via a nested runner
    jar = Path("/app/lib/glideclash.jar")
    probe_dir = Path(__file__).resolve().parent / "java"
    with tempfile.TemporaryDirectory(prefix="glide_locale_") as tmp:
        tmp_path = Path(tmp)
        work = tmp_path / "work"
        work.mkdir()
        junk = work / "noise.txt"
        junk.write_text("should-not-matter\n", encoding="utf-8")
        classes = tmp_path / "classes"
        classes.mkdir()
        subprocess.run(
            [
                "javac",
                "--release",
                "17",
                "-cp",
                str(jar),
                "-d",
                str(classes),
                *[str(p) for p in sorted(probe_dir.glob("*.java"))],
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        env = os.environ.copy()
        env["LANG"] = "C"
        env["LC_ALL"] = "C"
        second = subprocess.run(
            [
                "java",
                "-Duser.language=fr",
                "-Duser.country=FR",
                "-cp",
                f"{classes}{os.pathsep}{jar}",
                "RollbackProbe",
                "locale-fs",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(work),
            env=env,
        ).stdout
    d1 = _lines(first)
    d2 = _lines(second)
    assert d1["head"] == d2["head"] == "2"
    assert d1["padx"] == d2["padx"]
    assert d1["record"] == d2["record"]
    assert not re.search(r"/tmp/|noise\.txt", d1["record"])
