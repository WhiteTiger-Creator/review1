"""Verifier suite for the umber kiln parcel engraver."""

from __future__ import annotations

import hashlib

from conftest import (
    CASES,
    INDEX,
    MANIFEST,
    TMP,
    assert_lf_final_newline,
    assert_no_products,
    assert_only_products,
    assert_tmp_clean,
    choose_mirror,
    copy_case,
    expect_failure,
    expect_success,
    parcel_digests,
    parse_index,
    parse_manifest,
    run_clean,
    run_engrave,
    shard_totals,
)


def test_ember_batch_index_matches_shard_totals(clean_workspace):
    """Recomputes own shard totals, BROTLI notes, and notice-ordered lane bids."""
    idx_txt, _ = expect_success("ember_batch")
    rows = parse_index(idx_txt)
    totals = shard_totals(CASES / "ember_batch")
    by_id = {r["crate_id"]: r for r in rows}
    assert by_id["CRATE_A"]["byte_total"] == str(totals["CRATE_A"][1])
    assert by_id["CRATE_B"]["byte_total"] == str(totals["CRATE_B"][1])
    assert by_id["CRATE_C"]["byte_total"] == str(totals["CRATE_C"][1])
    assert by_id["CRATE_A"]["shard_count"] == str(totals["CRATE_A"][0])
    assert by_id["CRATE_B"]["shard_count"] == str(totals["CRATE_B"][0])
    assert by_id["CRATE_C"]["shard_count"] == str(totals["CRATE_C"][0])
    assert by_id["CRATE_A"]["index_note"] == "BROTLI"
    assert by_id["CRATE_B"]["index_note"] == "BROTLI"
    assert by_id["CRATE_C"]["index_note"] == "BROTLI"
    # Notice bid order A,C,B → A LANE1, C LANE1, B LANE2 (not crate_priority desc)
    assert by_id["CRATE_A"]["lane_id"] == "LANE1"
    assert by_id["CRATE_C"]["lane_id"] == "LANE1"
    assert by_id["CRATE_B"]["lane_id"] == "LANE2"


def test_seal_manifest_matches_mirror_and_notice_choice(clean_workspace):
    """Checks mirror selection, root seals, and root-to-leaf public text."""
    _, seal_txt = expect_success("ember_batch")
    rows = parse_manifest(seal_txt)
    by_id = {r["crate_id"]: r for r in rows}
    assert by_id["CRATE_A"]["mirror_id"] == choose_mirror(CASES / "ember_batch", "CRATE_A")
    assert by_id["CRATE_A"]["mirror_id"] == "M_BETA_LO"
    assert by_id["CRATE_B"]["mirror_id"] == "M_GAMMA_LO"
    assert by_id["CRATE_C"]["mirror_id"] == "M_DEL_LO"
    assert by_id["CRATE_A"]["public_seal_text"] == "root_seal_ok"
    assert by_id["CRATE_B"]["public_seal_text"] == "root_seal_ok#child_b_text"
    assert by_id["CRATE_C"]["public_seal_text"] == "root_seal_ok#child_b_text#child_c_text"
    assert by_id["CRATE_B"]["seal_token"] == "KILN_SEAL"
    assert by_id["CRATE_C"]["seal_token"] == "KILN_SEAL"


def test_crate_index_header_widths_and_lf(clean_workspace):
    """Validates crate.index header, right-aligned numerics, LF, final newline."""
    idx_txt, _ = expect_success("ember_batch")
    assert_lf_final_newline(idx_txt)
    lines = idx_txt.splitlines()
    assert lines[0] == "crate_id family shard_count byte_total lane_id release_tier index_note"
    totals = shard_totals(CASES / "ember_batch")
    for line in lines[1:]:
        assert len(line) == 60
        crate_id = line[0:10].rstrip(" ")
        sc = line[20:24]
        bt = line[24:32]
        count, own = totals[crate_id]
        assert sc == str(count).rjust(4), f"shard_count misaligned/wrong: {sc!r}"
        assert bt == str(own).rjust(8), f"byte_total misaligned/wrong: {bt!r}"


def test_seal_manifest_header_widths_and_lf(clean_workspace):
    """Validates seal.manifest header and line formatting."""
    _, seal_txt = expect_success("ember_batch")
    assert_lf_final_newline(seal_txt)
    lines = seal_txt.splitlines()
    assert lines[0].startswith("crate_id seal_token mirror_id notice_fence")
    for line in lines[1:]:
        assert len(line) == 94  # 10+12+10+12+10+40


def test_shard_order_gap_is_detected(clean_workspace):
    """Missing shard order makes the set inconsistent."""
    expect_failure("shard_order_gap")


def test_trusted_mirror_receipt_allows_reuse(clean_workspace):
    """Confirms humble trusted match on dominant shard permits inclusion."""
    _, seal_txt = expect_success("mirror_receipt_choice")
    rows = parse_manifest(seal_txt)
    assert {r["crate_id"]: r["mirror_id"] for r in rows}["CRATE_A"] == "M_BETA_LO"


def test_disagreeing_mirrors_leave_products_empty(clean_workspace):
    """Conflicting trusted receipt digests clear products."""
    expect_failure("disagreeing_mirrors")


def test_notice_fence_chain_propagates_to_child(clean_workspace):
    """Verifies multi-hop fence inheritance with root-to-leaf public text."""
    _, seal_txt = expect_success("notice_fence_chain")
    rows = parse_manifest(seal_txt)
    by_id = {r["crate_id"]: r for r in rows}
    assert by_id["CRATE_C"]["notice_fence"] == "FENCE_ROOT"
    assert by_id["CRATE_C"]["public_seal_text"] == "root_seal_ok#child_b_text#child_c_text"


def test_conflicting_notice_fence_leaves_products_empty(clean_workspace):
    """Family-level notice conflict prevents publication."""
    expect_failure("conflicting_notice_fence")


def test_inherit_fence_mismatch_leaves_products_empty(clean_workspace):
    """Illegal local fence while inheriting clears products."""
    expect_failure("inherit_fence_mismatch")


def test_lane_capacity_edge_accepts_exact_fill(clean_workspace):
    """Dual-lane greedy bidding remains consistent on the ember residual."""
    idx_txt, _ = expect_success("lane_capacity_edge")
    by_id = {r["crate_id"]: r for r in parse_index(idx_txt)}
    assert by_id["CRATE_B"]["lane_id"] == "LANE2"
    assert by_id["CRATE_A"]["lane_id"] == "LANE1"


def test_greedy_lane_order_trap_uses_notice_not_crate_priority(clean_workspace):
    """Lane bid walk follows ascending notice_priority then crate_id."""
    idx_txt, _ = expect_success("greedy_lane_order_trap")
    by_id = {r["crate_id"]: r for r in parse_index(idx_txt)}
    assert by_id["CRATE_B"]["lane_id"] == "LANE2"
    assert by_id["CRATE_C"]["lane_id"] == "LANE1"


def test_family_scoped_contrib_ignores_cross_family_ancestors(clean_workspace):
    """Lane load excludes cross-family parents while fence still inherits."""
    idx_txt, seal_txt = expect_success("family_scoped_contrib")
    by_id = {r["crate_id"]: r for r in parse_index(idx_txt)}
    assert by_id["CRATE_B"]["lane_id"] == "LANE1"
    assert by_id["CRATE_B"]["byte_total"] == "100"
    seal = {r["crate_id"]: r for r in parse_manifest(seal_txt)}
    assert seal["CRATE_B"]["notice_fence"] == "FENCE_KIN"
    assert seal["CRATE_B"]["public_seal_text"] == "amber_root#ember_child"
    assert seal["CRATE_B"]["seal_token"] == "UMBER_SEAL"


def test_tightest_lane_residual_breaks_priority_ties(clean_workspace):
    """Equal lane_priority selects the smallest residual capacity."""
    idx_txt, _ = expect_success("tightest_lane_residual")
    by_id = {r["crate_id"]: r for r in parse_index(idx_txt)}
    assert by_id["CRATE_T"]["lane_id"] == "LANE_Z"


def test_stamp_election_uses_notice_priority_on_tie(clean_workspace):
    """Equal stamp_priority elects via lowest notice_priority."""
    idx_txt, _ = expect_success("stamp_notice_tie")
    for r in parse_index(idx_txt):
        assert r["index_note"] == "GZIP"


def test_mirror_affinity_breaks_priority_ties(clean_workspace):
    """Equal mirror_priority prefers crate-wide affinity before id order."""
    _, seal_txt = expect_success("mirror_affinity_tie")
    rows = parse_manifest(seal_txt)
    assert rows[0]["mirror_id"] == "M_AFF"
    assert rows[0]["mirror_id"] == choose_mirror(CASES / "mirror_affinity_tie", "CRATE_A")


def test_overflowing_lane_leaves_products_empty(clean_workspace):
    """Infeasible bid after fill clears products."""
    expect_failure("overflowing_lane")


def test_lane_bid_infeasible_leaves_products_empty(clean_workspace):
    """Single undersized lane with no alternate bid clears products."""
    expect_failure("lane_bid_infeasible")


def test_checksum_alphabet_rejects_bad_character(clean_workspace):
    """Digest outside allowed alphabet clears outputs."""
    expect_failure("bad_checksum_alphabet")


def test_release_tier_step_hold_blocks_jump(clean_workspace):
    """Crate cannot jump more than one tier beyond its parent."""
    expect_failure("tier_step_hold")


def test_index_sort_uses_descending_crate_priority(clean_workspace):
    """Index orders by checksum then descending crate_priority."""
    idx_txt, _ = expect_success("ember_batch")
    rows = parse_index(idx_txt)
    assert [r["crate_id"] for r in rows] == ["CRATE_A", "CRATE_B", "CRATE_C"]


def test_index_sort_puts_lower_checksum_family_first(clean_workspace):
    """Dual-family fixture: amber checksum_priority 10 before ember 40."""
    idx_txt, _ = expect_success("dual_family_sort")
    rows = parse_index(idx_txt)
    assert rows[0]["crate_id"] == "CRATE_D"
    assert [r["crate_id"] for r in rows[1:]] == ["CRATE_A", "CRATE_B", "CRATE_C"]


def test_manifest_sort_uses_fence_then_notice(clean_workspace):
    """Manifest orders by fence, then notice_priority, then id."""
    _, seal_txt = expect_success("ember_batch")
    rows = parse_manifest(seal_txt)
    # notice priorities 10,20,30 → A,C,B
    assert [r["crate_id"] for r in rows] == ["CRATE_A", "CRATE_C", "CRATE_B"]


def test_stamp_sheet_override_changes_family_election(clean_workspace):
    """stamps.tsv priorities override habit; GZIP wins when BROTLI demoted."""
    idx_txt, _ = expect_success("stamp_sheet_override")
    for r in parse_index(idx_txt):
        assert r["index_note"] == "GZIP"


def test_compose_width_overflow_leaves_products_empty(clean_workspace):
    """Chain-folded public seal text that exceeds width clears products."""
    expect_failure("compose_width_overflow")


def test_shuffled_parcel_sheets_keep_hashes(clean_workspace):
    """Reorders all parcel tables and compares product hashes."""
    a_idx, a_seal = expect_success("ember_batch")
    b_idx, b_seal = expect_success("shuffled_parcels")
    assert hashlib.sha256(a_idx.encode()).hexdigest() == hashlib.sha256(b_idx.encode()).hexdigest()
    assert hashlib.sha256(a_seal.encode()).hexdigest() == hashlib.sha256(b_seal.encode()).hexdigest()


def test_second_engrave_run_is_byte_identical(clean_workspace):
    """Repeats a consistent set and compares artifact bytes."""
    copy_case("ember_batch")
    run_clean()
    assert run_engrave().returncode == 0
    first_idx = INDEX.read_bytes()
    first_seal = MANIFEST.read_bytes()
    assert run_engrave().returncode == 0
    assert INDEX.read_bytes() == first_idx
    assert MANIFEST.read_bytes() == first_seal
    assert_tmp_clean()
    assert_only_products()


def test_parcel_inputs_remain_unchanged(clean_workspace):
    """Hashes /app/parcels sheets before and after engraving."""
    copy_case("ember_batch")
    before = parcel_digests()
    run_clean()
    assert run_engrave().returncode == 0
    after = parcel_digests()
    assert before == after


def test_repeated_crate_id_leaves_no_release_products(clean_workspace):
    """Duplicate crate ids clear products."""
    expect_failure("repeated_crate_id")


def test_orphan_shard_leaves_no_release_products(clean_workspace):
    """Shard referencing absent crate prevents publication."""
    expect_failure("orphan_shard")


def test_unknown_compression_stamp_leaves_no_release_products(clean_workspace):
    """Undeclared stamp relative to stamps.tsv clears outputs."""
    expect_failure("unknown_compression_stamp")


def test_missing_seal_wording_leaves_no_release_products(clean_workspace):
    """Missing local public seal text prevents publication."""
    expect_failure("missing_seal_wording")


def test_index_width_overflow_leaves_no_release_products(clean_workspace):
    """Rendered field too wide clears products."""
    expect_failure("index_width_overflow")


def test_stale_products_removed_after_inconsistent_set(clean_workspace):
    """Good products vanish after an inconsistent case."""
    expect_success("ember_batch")
    assert INDEX.is_file() and MANIFEST.is_file()
    expect_failure("orphan_shard")
    assert_no_products()


def test_forced_vala_failure_leaves_no_release_products(clean_workspace):
    """Simulated nonzero Vala run leaves no partial products."""
    expect_failure("forced_vala_failure")


def test_engraving_tmp_returns_to_placeholder(clean_workspace):
    """Confirms engraving chips are removed after both outcomes."""
    expect_success("ember_batch")
    assert_tmp_clean()
    expect_failure("shard_order_gap")
    assert_tmp_clean()
    leftovers = [p.name for p in TMP.iterdir() if p.name != ".keep"]
    assert leftovers == []
