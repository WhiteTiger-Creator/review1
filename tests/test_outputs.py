"""Verifier for unix-peer-cred-cache-stale."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ENV_ROOT = Path("/app/environment")
OUTPUT_DIR = Path("/app/output")

KAIRO_UID = 4101
VEXA_UID = 4202
DROP_MASK = 0x00FF
KAIRO_SUPP = 0x00FF
VEXA_SUPP = 0x0F00
ALPHA = "alpha-sock"
CHILD = "beta-child"
RUN_SOCK = "/app/environment/state/run.sock"
SHIFT_CYCLES = 3
OUTPUT_FILES = (
    "binding_transcript.json",
    "auth_trace.json",
    "probe_report.jsonl",
    "auth_journal.jsonl",
    "converge_report.json",
)


def _hex_digest(material: str, nbytes: int) -> str:
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-hex"],
        input=material.encode(),
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode().strip().split()[-1][: nbytes * 2]


def _mark_hex(uid: int, tag: str) -> str:
    return _hex_digest(f"{tag}:{uid}", 8)


def _cookie(path: str, gen: int, arm_epoch: int) -> str:
    return _hex_digest(f"{path}|{gen}|{arm_epoch}", 8)


def _cookie_gen_only(path: str, gen: int) -> str:
    return _hex_digest(f"{path}|{gen}", 8)


def _lane_hex(slot: str, path: str, cookie: str, uid: int, supp: int, mark: str) -> str:
    return _hex_digest(f"{slot}|{path}|{cookie}|{uid}|{supp}|{mark}", 8)


KAIRO_MARK = _mark_hex(KAIRO_UID, "kairo")
VEXA_MARK = _mark_hex(VEXA_UID, "vexa")
POST_DROP_SUPP = KAIRO_SUPP & ~DROP_MASK
LIVE_COOKIE = _cookie(RUN_SOCK, SHIFT_CYCLES, SHIFT_CYCLES)


def run_repro(cycles: int = SHIFT_CYCLES) -> None:
    env = os.environ.copy()
    env.update(
        {
            "ENV_ROOT": str(ENV_ROOT),
            "OUTPUT_DIR": str(OUTPUT_DIR),
            "SHIFT_CYCLES": str(cycles),
        }
    )
    subprocess.run(
        ["bash", "/app/environment/scripts/repro_shift_cycle.sh"],
        check=True,
        env=env,
    )


def run_gated_resume(cycles: int = SHIFT_CYCLES) -> None:
    subprocess.run(
        [
            "/app/bin/gated",
            "-root",
            str(ENV_ROOT),
            "-out",
            str(OUTPUT_DIR),
            "-cycles",
            str(cycles),
        ],
        check=True,
    )


def load_json(name: str):
    return json.loads((OUTPUT_DIR / name).read_text(encoding="utf-8"))


def load_jsonl(name: str):
    lines = (OUTPUT_DIR / name).read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def rows_for_ref(rows, ref: str):
    return [r for r in rows if r.get("slot_ref") == ref]


def test_bind_cookie_chains_attach_policy_epoch():
    """Bind cookies must chain inode generation with attach policy_epoch for each cycle."""
    run_repro()
    probes = load_jsonl("probe_report.jsonl")
    alpha_cookies = [p["bind_cookie"] for p in probes if p["slot_ref"] == ALPHA]
    assert len(alpha_cookies) == SHIFT_CYCLES
    expected = [_cookie(RUN_SOCK, g, g) for g in range(1, SHIFT_CYCLES + 1)]
    assert alpha_cookies == expected
    assert alpha_cookies[-1] == LIVE_COOKIE
    assert len(set(alpha_cookies)) == SHIFT_CYCLES


def test_cookie_arm_epoch_diverges_from_gen_only_digest():
    """Armed cookies must not collapse to generation-only digest material."""
    run_repro()
    probes = load_jsonl("probe_report.jsonl")
    alpha_cookies = [p["bind_cookie"] for p in probes if p["slot_ref"] == ALPHA]
    gen_only = [_cookie_gen_only(RUN_SOCK, g) for g in range(1, SHIFT_CYCLES + 1)]
    assert alpha_cookies != gen_only
    for armed, plain in zip(alpha_cookies, gen_only, strict=True):
        assert armed != plain


def test_child_vault_key_binds_attach_epoch():
    """Child vault keys must bind attach policy_epoch so sibling lane fingerprints diverge."""
    run_repro()
    traces = load_json("auth_trace.json")
    hot_alpha = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    child_rows = rows_for_ref(traces, CHILD)
    assert hot_alpha and child_rows
    parent = hot_alpha[-1]
    child = child_rows[-1]
    assert child["bind_cookie"] == parent["bind_cookie"] == LIVE_COOKIE
    assert child["seal_hex"] != parent["seal_hex"]
    want_child = _lane_hex(CHILD, RUN_SOCK, LIVE_COOKIE, VEXA_UID, POST_DROP_SUPP, "vexa")
    assert child["seal_hex"] == want_child
    probes = load_jsonl("probe_report.jsonl")
    child_probes = [p for p in probes if p["slot_ref"] == CHILD]
    assert child_probes[-1]["seal_match"] == 0


def test_facet_republishes_on_mask_only_change():
    """Hot transition must republish the facet when only supp_mask and seal_hex change under the same cookie."""
    run_repro()
    traces = load_json("auth_trace.json")
    hot = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    assert hot
    last = hot[-1]
    assert last["supp_mask"] == POST_DROP_SUPP
    assert last["seal_hex"] == _lane_hex(ALPHA, RUN_SOCK, LIVE_COOKIE, VEXA_UID, POST_DROP_SUPP, "vexa")
    probes = load_jsonl("probe_report.jsonl")
    alpha_probes = [p for p in probes if p["slot_ref"] == ALPHA]
    assert alpha_probes[-1]["seal_match"] == 1
    assert alpha_probes[-1]["current_uid"] == VEXA_UID


def test_child_epoch_uses_attach_bind_snapshot():
    """Child policy_epoch must trail the attach bind snapshot within each cycle, not a later counter."""
    run_repro()
    binds = load_json("binding_transcript.json")
    for cycle_idx in range(SHIFT_CYCLES):
        alpha_rows = rows_for_ref(binds, ALPHA)
        child_rows = rows_for_ref(binds, CHILD)
        assert len(alpha_rows) > cycle_idx
        assert len(child_rows) > cycle_idx
        attach_epoch = alpha_rows[cycle_idx]["policy_epoch"]
        child_epoch = child_rows[cycle_idx]["policy_epoch"]
        assert child_epoch == attach_epoch + 1


def test_lane_fingerprint_binds_cookie_and_slot():
    """Post-shift alpha fingerprint binds slot_ref and the live armed bind cookie."""
    run_repro()
    traces = load_json("auth_trace.json")
    hot = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    assert hot
    last = hot[-1]
    want = _lane_hex(ALPHA, RUN_SOCK, LIVE_COOKIE, VEXA_UID, POST_DROP_SUPP, "vexa")
    assert last["seal_hex"] == want
    assert last["supp_mask"] == POST_DROP_SUPP
    assert last["bind_cookie"] == LIVE_COOKIE


def test_lane_digest_uses_cleared_mask():
    """Lane fingerprints must hash supplemental masks after drop-bit clearing."""
    run_repro()
    traces = load_json("auth_trace.json")
    hot = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    assert hot
    last = hot[-1]
    uncleared = _lane_hex(ALPHA, RUN_SOCK, LIVE_COOKIE, VEXA_UID, VEXA_SUPP, "vexa")
    assert last["seal_hex"] != uncleared
    assert last["seal_hex"] == _lane_hex(
        ALPHA, RUN_SOCK, LIVE_COOKIE, VEXA_UID, POST_DROP_SUPP, "vexa"
    )


def test_hot_drop_clears_mask_and_facet_agrees():
    """Hot transition clears drop_mask bits and probe current view matches post-clear uid."""
    run_repro()
    traces = load_json("auth_trace.json")
    hot = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    assert hot
    last = hot[-1]
    assert last["supp_mask"] & DROP_MASK == 0
    assert last["supp_mask"] == POST_DROP_SUPP
    probes = load_jsonl("probe_report.jsonl")
    alpha_probes = [p for p in probes if p["slot_ref"] == ALPHA]
    assert alpha_probes[-1]["current_uid"] == VEXA_UID
    assert alpha_probes[-1]["seal_match"] == 1


def test_vault_live_cookie_pins_probe():
    """After rematerialization, probes pin the live-cookie vault sample with seal_match."""
    run_repro()
    probes = load_jsonl("probe_report.jsonl")
    alpha_probes = [p for p in probes if p["slot_ref"] == ALPHA]
    assert alpha_probes
    last = alpha_probes[-1]
    assert last["seal_match"] == 1
    assert last["cred_gap"] == 0
    assert last["current_uid"] == last["pinned_uid"] == VEXA_UID
    assert last["bind_cookie"] == LIVE_COOKIE


def snapshot_outputs() -> dict[str, bytes]:
    return {name: (OUTPUT_DIR / name).read_bytes() for name in OUTPUT_FILES}


def test_sibling_probe_seal_match_requires_full_agreement():
    """Sibling slot probes keep seal_match at 0 when lane fingerprints differ but uids agree."""
    run_repro()
    probes = load_jsonl("probe_report.jsonl")
    child_probes = [p for p in probes if p["slot_ref"] == CHILD]
    assert child_probes
    last = child_probes[-1]
    assert last["cred_gap"] == 0
    assert last["pinned_uid"] == last["current_uid"] == VEXA_UID
    assert last["bind_cookie"] == LIVE_COOKIE
    assert last["seal_match"] == 0


def test_child_vault_isolates_shared_path():
    """Child ref restamps under its own slot even when path string matches parent."""
    run_repro()
    traces = load_json("auth_trace.json")
    hot_alpha = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    child_rows = rows_for_ref(traces, CHILD)
    assert hot_alpha and child_rows
    parent = hot_alpha[-1]
    child = child_rows[-1]
    assert child["mark_digest_hex"] == parent["mark_digest_hex"] == VEXA_MARK
    assert child["supp_mask"] == parent["supp_mask"] == POST_DROP_SUPP
    assert child["bind_cookie"] == parent["bind_cookie"] == LIVE_COOKIE
    assert child["seal_hex"] != parent["seal_hex"]
    want_child = _lane_hex(CHILD, RUN_SOCK, LIVE_COOKIE, VEXA_UID, POST_DROP_SUPP, "vexa")
    assert child["seal_hex"] == want_child
    assert child["seal_hex"] != _lane_hex(ALPHA, RUN_SOCK, LIVE_COOKIE, VEXA_UID, POST_DROP_SUPP, "vexa")


def test_journal_once_intake_rebind():
    """Multi-cycle export keeps one intake and one rebind across the full journal."""
    run_repro()
    journal = load_jsonl("auth_journal.jsonl")
    ops = [row["op"] for row in journal]
    assert ops.count("intake") == 1
    assert ops.count("rebind") == 1
    rebind = next(row for row in journal if row["op"] == "rebind")
    assert rebind["mark"] == "vexa"
    assert rebind["supp_mask"] == POST_DROP_SUPP
    armed_cookie = _cookie(RUN_SOCK, 2, 2)
    assert rebind["bind_cookie"] == armed_cookie
    assert rebind["seal_hex"] == _lane_hex(
        ALPHA, RUN_SOCK, armed_cookie, VEXA_UID, POST_DROP_SUPP, "vexa"
    )


def test_journal_rebind_gated_on_listener_seal():
    """Rebind rows must carry armed cookies from sealed listener cycles, not pre-shift material."""
    run_repro()
    journal = load_jsonl("auth_journal.jsonl")
    rebind_rows = [row for row in journal if row["op"] == "rebind"]
    assert len(rebind_rows) == 1
    rebind = rebind_rows[0]
    assert rebind["bind_cookie"] == _cookie(RUN_SOCK, 2, 2)
    assert rebind["bind_cookie"] != _cookie(RUN_SOCK, 1, 1)
    probes = load_jsonl("probe_report.jsonl")
    alpha_cookies = [p["bind_cookie"] for p in probes if p["slot_ref"] == ALPHA]
    assert rebind["bind_cookie"] in alpha_cookies


def test_resume_freezes_existing_exports():
    """Resumed gated against existing outputs must not add rows and keeps post-shift state."""
    if OUTPUT_DIR.exists():
        for p in OUTPUT_DIR.iterdir():
            p.unlink()
    run_repro()
    before = snapshot_outputs()
    run_gated_resume()
    after = snapshot_outputs()
    assert after == before
    traces = load_json("auth_trace.json")
    hot = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK]
    assert hot
    assert hot[-1]["supp_mask"] & DROP_MASK == 0
    assert hot[-1]["bind_cookie"] == LIVE_COOKIE
    probes = load_jsonl("probe_report.jsonl")
    alpha_probes = [p for p in probes if p["slot_ref"] == ALPHA]
    assert alpha_probes
    last = alpha_probes[-1]
    assert last["cred_gap"] == 0
    assert last["current_uid"] == last["pinned_uid"] == VEXA_UID
    assert last["seal_match"] == 1


def test_facet_publish_survives_hot_transition_chain():
    """Authorization facet keeps attach slot_ref and seal agreement across every post-intake cycle."""
    run_repro()
    probes = load_jsonl("probe_report.jsonl")
    alpha_probes = [p for p in probes if p["slot_ref"] == ALPHA]
    assert len(alpha_probes) == SHIFT_CYCLES
    for probe in alpha_probes[1:]:
        assert probe["seal_match"] == 1
        assert probe["cred_gap"] == 0
        assert probe["current_uid"] == VEXA_UID
    armed = [_cookie(RUN_SOCK, g, g) for g in range(1, SHIFT_CYCLES + 1)]
    assert [p["bind_cookie"] for p in alpha_probes] == armed


def test_cross_module_convergence():
    """Cookie, drop, child isolation, facet pin, and journal authorities converge."""
    run_repro()
    conv = load_json("converge_report.json")
    assert conv["cycles"]
    assert len(conv["cycles"]) == SHIFT_CYCLES
    final = conv["cycles"][-1]
    assert final["scope_agreement_count"] >= 3
    probes = load_jsonl("probe_report.jsonl")
    last_probe = [p for p in probes if p["slot_ref"] == ALPHA][-1]
    assert last_probe["cred_gap"] == 0
    assert last_probe["seal_match"] == 1
    assert last_probe["bind_cookie"] == LIVE_COOKIE
    traces = load_json("auth_trace.json")
    child = rows_for_ref(traces, CHILD)[-1]
    hot = [r for r in rows_for_ref(traces, ALPHA) if r["mark_digest_hex"] == VEXA_MARK][-1]
    assert child["seal_hex"] != hot["seal_hex"]
    assert hot["supp_mask"] & DROP_MASK == 0
    assert hot["bind_cookie"] == LIVE_COOKIE
    journal = load_jsonl("auth_journal.jsonl")
    assert len(journal) == final["journal_rows"]
    binds = load_json("binding_transcript.json")
    assert len(binds) == final["transcript_rows"]
    assert len(traces) == final["trace_rows"]
