#!/usr/bin/env python3
"""Generate parcel / smoke TSV fixtures for umber-kiln-parcel-engraver."""

from __future__ import annotations

import csv
import shutil
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "environment" / "app"
PARCELS = APP / "parcels"
SMOKE = APP / "engraver" / "smoke"
CASES = PARCELS / "cases"

SHEETS = [
    "stamps.tsv",
    "crates.tsv",
    "shards.tsv",
    "mirrors.tsv",
    "notices.tsv",
    "lanes.tsv",
    "checksums.tsv",
    "tiers.tsv",
    "widths.tsv",
]

HEADERS = {
    "stamps.tsv": ["stamp", "stamp_priority"],
    "crates.tsv": [
        "crate_id",
        "family",
        "compression_stamp",
        "release_tier",
        "crate_priority",
        "seal_token",
    ],
    "shards.tsv": [
        "shard_id",
        "crate_id",
        "shard_order",
        "input_name",
        "byte_count",
        "shard_digest",
    ],
    "mirrors.tsv": [
        "input_name",
        "mirror_id",
        "receipt_digest",
        "mirror_trust",
        "mirror_priority",
    ],
    "notices.tsv": [
        "crate_id",
        "notice_fence",
        "inherited_from",
        "notice_priority",
        "public_text",
    ],
    "lanes.tsv": [
        "lane_id",
        "crate_id",
        "capacity_bytes",
        "used_bytes",
        "lane_priority",
        "lane_note",
    ],
    "checksums.tsv": [
        "alphabet_id",
        "allowed_characters",
        "digest_width",
        "checksum_priority",
    ],
    "tiers.tsv": [
        "release_tier",
        "predecessor_tier",
        "tier_priority",
        "tier_wording",
    ],
    "widths.tsv": ["product", "column", "width"],
}


def write_tsv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow(row)


def write_bundle(dest: Path, data: dict[str, list[list[object]]]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for sheet in SHEETS:
        write_tsv(dest / sheet, HEADERS[sheet], data[sheet])


def standard_stamps() -> list[list[object]]:
    return [["ZIP", 10], ["GZIP", 20], ["BROTLI", 30], ["XZ", 40]]


def standard_tiers() -> list[list[object]]:
    return [
        ["draft", "", 10, "draft_hold"],
        ["candidate", "draft", 20, "candidate_hold"],
        ["gold", "candidate", 30, "gold_release"],
    ]


def standard_widths(public_w: int = 40) -> list[list[object]]:
    return [
        ["crate.index", "crate_id", 10],
        ["crate.index", "family", 10],
        ["crate.index", "shard_count", 4],
        ["crate.index", "byte_total", 8],
        ["crate.index", "lane_id", 8],
        ["crate.index", "release_tier", 12],
        ["crate.index", "index_note", 8],
        ["seal.manifest", "crate_id", 10],
        ["seal.manifest", "seal_token", 12],
        ["seal.manifest", "mirror_id", 10],
        ["seal.manifest", "notice_fence", 12],
        ["seal.manifest", "checksum_alphabet", 10],
        ["seal.manifest", "public_seal_text", public_w],
    ]


def standard_checksums() -> list[list[object]]:
    return [
        ["amber", "abcdef0123456789", 8, 10],
        ["ember", "abcdef0123456789", 8, 40],
    ]


def dual_lane_candidates() -> list[list[object]]:
    """Each crate bids on LANE1 (pri 20) and LANE2 (pri 10); cap 800 used 0."""
    rows = []
    for cid in ("CRATE_A", "CRATE_B", "CRATE_C"):
        rows.append(["LANE1", cid, 800, 0, 20, "north"])
        rows.append(["LANE2", cid, 800, 0, 10, "south"])
    return rows


def base_ember() -> dict[str, list[list[object]]]:
    """Notice bid order A(10),C(20),B(30).

    contrib A=250 B=450 C=530 (same-family ancestors)
    Correct lanes: A→LANE1, C→LANE1, B→LANE2
    Root-to-leaf public C: root_seal_ok#child_b_text#child_c_text
    """
    return {
        "stamps.tsv": standard_stamps(),
        "crates.tsv": [
            ["CRATE_A", "ember", "GZIP", "draft", 30, "KILN_SEAL"],
            ["CRATE_B", "ember", "BROTLI", "candidate", 20, "AMBER_SEAL"],
            ["CRATE_C", "ember", "ZIP", "gold", 10, "BRONZE_SEAL"],
        ],
        "shards.tsv": [
            ["S1", "CRATE_A", 1, "in_alpha", 100, "aabbcc01"],
            ["S2", "CRATE_A", 2, "in_beta", 150, "ddeeff02"],
            ["S3", "CRATE_B", 1, "in_gamma", 200, "11223344"],
            ["S4", "CRATE_C", 1, "in_delta", 80, "55667788"],
        ],
        "mirrors.tsv": [
            ["in_alpha", "M_HIGH", "aabbcc01", "yes", 50],
            ["in_alpha", "M_LOW", "aabbcc01", "yes", 5],
            ["in_beta", "M_BETA_HI", "ddeeff02", "yes", 90],
            ["in_beta", "M_BETA_LO", "ddeeff02", "yes", 10],
            ["in_gamma", "M_GAMMA_HI", "11223344", "yes", 40],
            ["in_gamma", "M_GAMMA_LO", "11223344", "yes", 7],
            ["in_delta", "M_DEL_HI", "55667788", "yes", 25],
            ["in_delta", "M_DEL_LO", "55667788", "yes", 3],
        ],
        "notices.tsv": [
            ["CRATE_A", "FENCE_ROOT", "", 10, "root_seal_ok"],
            ["CRATE_B", "", "CRATE_A", 30, "child_b_text"],
            ["CRATE_C", "FENCE_ROOT", "CRATE_B", 20, "child_c_text"],
        ],
        "lanes.tsv": dual_lane_candidates(),
        "checksums.tsv": standard_checksums(),
        "tiers.tsv": standard_tiers(),
        "widths.tsv": standard_widths(),
    }


def clone(data: dict[str, list[list[object]]]) -> dict[str, list[list[object]]]:
    return deepcopy(data)


def main() -> None:
    if CASES.exists():
        shutil.rmtree(CASES)
    CASES.mkdir(parents=True)

    ember = base_ember()
    write_bundle(SMOKE, ember)
    write_bundle(PARCELS, ember)
    write_bundle(CASES / "ember_batch", ember)
    write_bundle(CASES / "notice_fence_chain", clone(ember))
    write_bundle(CASES / "lane_capacity_edge", clone(ember))
    write_bundle(CASES / "greedy_lane_order_trap", clone(ember))

    gap = clone(ember)
    gap["shards.tsv"][1][2] = 3
    write_bundle(CASES / "shard_order_gap", gap)

    skipped = clone(ember)
    skipped["shards.tsv"][0][2] = 2
    skipped["shards.tsv"][1][2] = 3
    write_bundle(CASES / "skipped_shard_order", skipped)

    mirror_choice = clone(ember)
    mirror_choice["mirrors.tsv"] = [
        ["in_alpha", "M_HIGH", "aabbcc01", "yes", 50],
        ["in_beta", "M_BETA_HI", "ddeeff02", "no", 90],
        ["in_beta", "M_BETA_LO", "ddeeff02", "yes", 10],
        ["in_gamma", "M_GAMMA_LO", "11223344", "yes", 7],
        ["in_delta", "M_DEL_LO", "55667788", "yes", 3],
    ]
    write_bundle(CASES / "mirror_receipt_choice", mirror_choice)

    shuffled = clone(ember)
    for sheet in SHEETS:
        if sheet != "widths.tsv":
            shuffled[sheet] = list(reversed(ember[sheet]))
    write_bundle(CASES / "shuffled_parcels", shuffled)

    rep = clone(ember)
    rep["crates.tsv"].append(["CRATE_A", "amber", "ZIP", "draft", 99, "UMBER_SEAL"])
    write_bundle(CASES / "repeated_crate_id", rep)

    orphan = clone(ember)
    orphan["shards.tsv"].append(["SX", "CRATE_Z", 1, "in_alpha", 10, "aabbcc01"])
    write_bundle(CASES / "orphan_shard", orphan)

    disagree = clone(ember)
    disagree["mirrors.tsv"] = [
        ["in_alpha", "M_HIGH", "aabbcc01", "yes", 50],
        ["in_alpha", "M_ALT", "ffffffff", "yes", 40],
        ["in_beta", "M_BETA_LO", "ddeeff02", "yes", 10],
        ["in_gamma", "M_GAMMA_LO", "11223344", "yes", 7],
        ["in_delta", "M_DEL_LO", "55667788", "yes", 3],
    ]
    write_bundle(CASES / "disagreeing_mirrors", disagree)

    unk = clone(ember)
    unk["crates.tsv"][0][2] = "LZ4"
    write_bundle(CASES / "unknown_compression_stamp", unk)

    conflict = clone(ember)
    conflict["crates.tsv"] = [
        ["CRATE_A", "ember", "GZIP", "draft", 30, "KILN_SEAL"],
        ["CRATE_B", "ember", "BROTLI", "draft", 20, "AMBER_SEAL"],
        ["CRATE_C", "ember", "ZIP", "draft", 10, "BRONZE_SEAL"],
    ]
    conflict["notices.tsv"] = [
        ["CRATE_A", "FENCE_ROOT", "", 10, "root_seal_ok"],
        ["CRATE_B", "FENCE_OTHER", "", 30, "child_b_text"],
        ["CRATE_C", "FENCE_ROOT", "", 20, "child_c_text"],
    ]
    write_bundle(CASES / "conflicting_notice_fence", conflict)

    inherit_bad = clone(ember)
    inherit_bad["notices.tsv"][1][1] = "FENCE_WRONG"
    write_bundle(CASES / "inherit_fence_mismatch", inherit_bad)

    # LANE2 too small for B's contrib 450 after correct bid needs it
    overflow = clone(ember)
    rows = []
    for cid in ("CRATE_A", "CRATE_B", "CRATE_C"):
        rows.append(["LANE1", cid, 800, 0, 20, "north"])
        rows.append(["LANE2", cid, 400, 0, 10, "south"])
    overflow["lanes.tsv"] = rows
    write_bundle(CASES / "overflowing_lane", overflow)

    bad_alpha = clone(ember)
    bad_alpha["shards.tsv"][0][5] = "aabbcc0z"
    write_bundle(CASES / "bad_checksum_alphabet", bad_alpha)

    missing = clone(ember)
    missing["notices.tsv"][1][4] = ""
    write_bundle(CASES / "missing_seal_wording", missing)

    wide = clone(ember)
    for row in wide["widths.tsv"]:
        if row[0] == "crate.index" and row[1] == "crate_id":
            row[2] = 3
    write_bundle(CASES / "index_width_overflow", wide)

    compose_wide = clone(ember)
    for row in compose_wide["widths.tsv"]:
        if row[0] == "seal.manifest" and row[1] == "public_seal_text":
            row[2] = 20
    write_bundle(CASES / "compose_width_overflow", compose_wide)

    forced = clone(ember)
    forced["crates.tsv"][0][2] = "vala_exit"
    write_bundle(CASES / "forced_vala_failure", forced)

    jump = clone(ember)
    jump["crates.tsv"][1][3] = "draft"
    jump["crates.tsv"][2][3] = "gold"
    write_bundle(CASES / "tier_step_hold", jump)

    stamp_override = clone(ember)
    stamp_override["stamps.tsv"] = [
        ["ZIP", 10],
        ["GZIP", 50],
        ["BROTLI", 15],
        ["XZ", 40],
    ]
    write_bundle(CASES / "stamp_sheet_override", stamp_override)

    dual = clone(ember)
    dual["crates.tsv"].append(["CRATE_D", "amber", "XZ", "draft", 5, "UMBER_SEAL"])
    dual["shards.tsv"].append(["S5", "CRATE_D", 1, "in_eps", 40, "99aabbcc"])
    dual["mirrors.tsv"].append(["in_eps", "M_EPS", "99aabbcc", "yes", 3])
    dual["notices.tsv"].append(["CRATE_D", "FENCE_AMB", "", 5, "amber_public"])
    dual["lanes.tsv"] = dual_lane_candidates() + [
        ["LANE3", "CRATE_D", 100, 0, 5, "east"],
    ]
    write_bundle(CASES / "dual_family_sort", dual)

    # no feasible lane for C after A takes the only room
    no_bid = clone(ember)
    no_bid["lanes.tsv"] = [
        ["LANE1", "CRATE_A", 300, 0, 20, "north"],
        ["LANE1", "CRATE_B", 300, 0, 20, "north"],
        ["LANE1", "CRATE_C", 300, 0, 20, "north"],
    ]
    write_bundle(CASES / "lane_bid_infeasible", no_bid)

    # Cross-family parent: family-scoped contrib keeps B at 100 (not 500).
    # LANE1 fits 100; all-ancestor sum would force LANE2.
    kin = {
        "stamps.tsv": standard_stamps(),
        "crates.tsv": [
            ["CRATE_A", "amber", "XZ", "draft", 10, "UMBER_SEAL"],
            ["CRATE_B", "ember", "BROTLI", "candidate", 20, "KILN_SEAL"],
        ],
        "shards.tsv": [
            ["S1", "CRATE_A", 1, "in_alpha", 400, "aabbcc01"],
            ["S2", "CRATE_B", 1, "in_gamma", 100, "11223344"],
        ],
        "mirrors.tsv": [
            ["in_alpha", "M_LOW", "aabbcc01", "yes", 5],
            ["in_gamma", "M_GAMMA_LO", "11223344", "yes", 7],
        ],
        "notices.tsv": [
            ["CRATE_A", "FENCE_KIN", "", 10, "amber_root"],
            ["CRATE_B", "", "CRATE_A", 20, "ember_child"],
        ],
        "lanes.tsv": [
            ["LANE_A", "CRATE_A", 400, 0, 10, "root"],
            ["LANE1", "CRATE_B", 150, 0, 20, "tight"],
            ["LANE2", "CRATE_B", 600, 0, 20, "wide"],
        ],
        "checksums.tsv": standard_checksums(),
        "tiers.tsv": standard_tiers(),
        "widths.tsv": standard_widths(),
    }
    write_bundle(CASES / "family_scoped_contrib", kin)

    # Equal lane_priority: tightest residual picks LANE_Z over lex-first LANE_X.
    tight = {
        "stamps.tsv": standard_stamps(),
        "crates.tsv": [
            ["CRATE_T", "ember", "BROTLI", "draft", 10, "KILN_SEAL"],
        ],
        "shards.tsv": [
            ["S1", "CRATE_T", 1, "in_gamma", 100, "11223344"],
        ],
        "mirrors.tsv": [
            ["in_gamma", "M_GAMMA_LO", "11223344", "yes", 7],
        ],
        "notices.tsv": [
            ["CRATE_T", "FENCE_T", "", 10, "tight_public"],
        ],
        "lanes.tsv": [
            ["LANE_X", "CRATE_T", 300, 0, 10, "loose"],
            ["LANE_Z", "CRATE_T", 100, 0, 10, "exact"],
        ],
        "checksums.tsv": standard_checksums(),
        "tiers.tsv": standard_tiers(),
        "widths.tsv": standard_widths(),
    }
    write_bundle(CASES / "tightest_lane_residual", tight)

    # Stamp priority ties: notice_priority elects GZIP; crate_priority would elect ZIP.
    stamp_tie = clone(ember)
    stamp_tie["stamps.tsv"] = [
        ["ZIP", 30],
        ["GZIP", 30],
        ["BROTLI", 10],
        ["XZ", 10],
    ]
    stamp_tie["crates.tsv"] = [
        ["CRATE_A", "ember", "ZIP", "draft", 5, "KILN_SEAL"],
        ["CRATE_B", "ember", "GZIP", "candidate", 50, "AMBER_SEAL"],
        ["CRATE_C", "ember", "ZIP", "gold", 40, "BRONZE_SEAL"],
    ]
    stamp_tie["notices.tsv"] = [
        ["CRATE_A", "FENCE_ROOT", "", 40, "root_seal_ok"],
        ["CRATE_B", "", "CRATE_A", 10, "child_b_text"],
        ["CRATE_C", "FENCE_ROOT", "CRATE_B", 20, "child_c_text"],
    ]
    write_bundle(CASES / "stamp_notice_tie", stamp_tie)

    # Mirror priority tie: affinity prefers M_AFF over lex-smaller M_AAA.
    affinity = {
        "stamps.tsv": standard_stamps(),
        "crates.tsv": [
            ["CRATE_A", "ember", "BROTLI", "draft", 10, "KILN_SEAL"],
        ],
        "shards.tsv": [
            ["S1", "CRATE_A", 1, "in_alpha", 50, "aabbcc01"],
            ["S2", "CRATE_A", 2, "in_beta", 150, "ddeeff02"],
        ],
        "mirrors.tsv": [
            ["in_alpha", "M_AFF", "aabbcc01", "yes", 10],
            ["in_alpha", "M_LOW", "aabbcc01", "yes", 5],
            ["in_beta", "M_AAA", "ddeeff02", "yes", 10],
            ["in_beta", "M_AFF", "ddeeff02", "yes", 10],
        ],
        "notices.tsv": [
            ["CRATE_A", "FENCE_AFF", "", 10, "aff_public"],
        ],
        "lanes.tsv": [
            ["LANE1", "CRATE_A", 200, 0, 10, "only"],
        ],
        "checksums.tsv": standard_checksums(),
        "tiers.tsv": standard_tiers(),
        "widths.tsv": standard_widths(),
    }
    write_bundle(CASES / "mirror_affinity_tie", affinity)

    print("fixtures written to", CASES)


if __name__ == "__main__":
    main()
