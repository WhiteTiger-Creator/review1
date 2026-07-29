"""Operational verifier for RAID Scrub Orchestration."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

CTL = Path("/opt/raid-scrub/bin/raidscrubctl")
APP = Path("/app")
DEFAULT_ROOT = Path("/app/work/raid-root")
DOCS = {
    "raid-contract.txt": APP / "raid-contract.txt",
    "array-inventory.txt": APP / "array-inventory.txt",
    "acceptance.txt": APP / "acceptance.txt",
    "scenarios.txt": APP / "scenarios.txt",
    "examples.txt": APP / "examples.txt",
}
BOOT_UUID = "11111111-2222-3333-4444-555555555555"
DATA_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAST_UUID = "ffffffff-0000-1111-2222-333333333333"
FOREIGN_UUID = "99999999-aaaa-bbbb-cccc-ddddeeeeffff"
EXPECTED_DIGEST = "f32ff0b321d2fd365abf5100042d285b5cc6c38ea71d998e51d2cebef8627f67"
FLOORS = {"bootmirror": 20000, "data5": 80000, "fast10": 60000}
WINDOWS = {"bootmirror": (1, 7), "data5": (8, 14), "fast10": (15, 28)}
GLOBAL_MAX = 200000
REPORT_FIELDS = [
    "arrays_known",
    "uuid_assembly_clean",
    "concurrent_scrubs_peak",
    "unsafe_repairs",
    "spare_activations",
    "resumed_scrubs",
    "duplicate_alerts",
    "recovery_alerts",
    "limits_restored",
    "budget_ok",
    "triage_ok",
    "adjacency_ok",
    "quorum_ok",
    "checkpoint_ok",
    "accepted",
]
ACCEPTED_REPORT = {
    "arrays_known": 3,
    "uuid_assembly_clean": True,
    "concurrent_scrubs_peak": 1,
    "unsafe_repairs": 0,
    "spare_activations": 1,
    "resumed_scrubs": 1,
    "duplicate_alerts": 0,
    "recovery_alerts": 1,
    "limits_restored": True,
    "budget_ok": True,
    "triage_ok": True,
    "adjacency_ok": True,
    "quorum_ok": True,
    "checkpoint_ok": True,
    "accepted": True,
}
ALLOWED_EVENTS = {
    "assemble",
    "foreign_excluded",
    "budget_applied",
    "budget_rejected",
    "triage_selected",
    "spare_activated",
    "spare_withheld",
    "checkpoint_quarantined",
    "checkpoint_rejected",
    "scrub_started",
    "scrub_resumed",
    "scrub_skipped_rebuild",
    "mismatch_observed",
    "repair_authorized",
    "repair_refused",
    "quorum_denied",
    "alert_degraded",
    "alert_recovery",
    "limits_restored",
    "lock_released",
    "read_error",
}


def _run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=check,
        timeout=timeout,
        env=merged,
    )


def _write_good_root(root: Path) -> None:
    """Clone the agent-edited staged root for isolated campaign variants."""
    if root.resolve() != DEFAULT_ROOT.resolve():
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(DEFAULT_ROOT, root)
    for rel in (
        "var/lib/raid-scrub/locks",
        "var/lib/raid-scrub/alerts",
        "var/lib/raid-scrub/checkpoints",
        "var/lib/raid-scrub/state",
        "etc/mdadm/mdadm.conf.d",
        "etc/systemd/system",
        "etc/raid-scrub",
        "usr/local/lib/raid-scrub",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)


def _apply(
    root: Path,
    out: Path,
    *extra: str,
    threshold: int | None = None,
    campaign: str | None = None,
    epoch: str | None = None,
) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    args = [str(CTL), "apply", "--root", str(root), "--output", str(out)]
    if threshold is not None:
        args.extend(["--threshold", str(threshold)])
    if campaign is not None:
        args.extend(["--campaign", campaign])
    if epoch is not None:
        args.extend(["--epoch", epoch])
    args.extend(extra)
    _run(args, env={"RAID_ROOT": str(root), "RAID_OUTPUT": str(out)})
    return json.loads((out / "raid-report.json").read_text(encoding="utf-8"))


def _events(out: Path) -> list[dict[str, object]]:
    lines = (out / "scrub-events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _state(out: Path) -> dict[str, object]:
    return json.loads((out / "array-state.json").read_text(encoding="utf-8"))


def _budget_path(root: Path) -> Path:
    return root / "etc/raid-scrub/io-budget.conf"


def _read_budget(root: Path) -> dict[str, int]:
    path = _budget_path(root)
    assert path.is_file(), "per-array io budget file missing"
    parsed: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        parsed[name.strip()] = int(value.strip())
    return parsed


def _set_budget(root: Path, boot: int, data: int, fast: int) -> None:
    _budget_path(root).write_text(
        f"bootmirror={boot}\ndata5={data}\nfast10={fast}\n", encoding="utf-8"
    )


def _set_timer_day(root: Path, name: str, day: str) -> None:
    (root / f"etc/systemd/system/raid-scrub-{name}.timer").write_text(
        f"[Timer]\nOnCalendar=*-*-{day} 03:00:00\nUnit=raid-scrub-{name}.service\n",
        encoding="utf-8",
    )


def _checkpoint(root: Path) -> Path:
    return root / "var/lib/raid-scrub/checkpoints/data5.offset"


@pytest.fixture()
def staged(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "raid-root"
    out = tmp_path / "output"
    _write_good_root(root)
    return root, out


# --------------------------------------------------------------------------
# integrity
# --------------------------------------------------------------------------


def test_raidscrub_toolchain_present() -> None:
    """Installed mdadm and smartctl binaries must be callable offline."""
    mdadm = shutil.which("mdadm") or "/sbin/mdadm"
    smartctl = shutil.which("smartctl") or "/usr/sbin/smartctl"
    assert Path(mdadm).is_file(), f"mdadm missing at {mdadm}"
    assert Path(smartctl).is_file(), f"smartctl missing at {smartctl}"
    md = _run([mdadm, "--version"])
    assert md.returncode == 0 or "mdadm" in (md.stdout + md.stderr).lower()
    sm = _run([smartctl, "--version"])
    assert "smartctl" in (sm.stdout + sm.stderr).lower()
    assert CTL.is_file() and os.access(CTL, os.X_OK)


def test_raidscrub_model_digest_pinned() -> None:
    """Protected array model digest must match the published topology hash."""
    completed = _run([str(CTL), "model-digest"])
    assert completed.stdout.strip() == EXPECTED_DIGEST
    inventory = DOCS["array-inventory.txt"].read_text(encoding="utf-8")
    begin = inventory.index("BEGIN_TOPOLOGY\n") + len("BEGIN_TOPOLOGY\n")
    end = inventory.index("\nEND_TOPOLOGY")
    block = "\n" + inventory[begin : end + 1]
    assert hashlib.sha256(block.encode()).hexdigest() == EXPECTED_DIGEST


def test_raidscrub_protected_assets_immutable(staged: tuple[Path, Path]) -> None:
    """Contract documents and the controller binary must survive an apply byte for byte."""
    root, out = staged
    before = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in DOCS.items()
    }
    ctl_before = hashlib.sha256(CTL.read_bytes()).hexdigest()
    _apply(root, out)
    for name, path in DOCS.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before[name], name
    assert hashlib.sha256(CTL.read_bytes()).hexdigest() == ctl_before
    assert stat.S_IMODE(CTL.stat().st_mode) & 0o222 == 0
    for path in DOCS.values():
        assert stat.S_IMODE(path.stat().st_mode) & 0o222 == 0


# --------------------------------------------------------------------------
# grammar
# --------------------------------------------------------------------------


def test_raidscrub_report_schema_exact(staged: tuple[Path, Path]) -> None:
    """raid-report.json must publish exactly the documented field set and types."""
    root, out = staged
    report = _apply(root, out)
    assert sorted(report.keys()) == sorted(REPORT_FIELDS)
    for key in (
        "arrays_known",
        "concurrent_scrubs_peak",
        "unsafe_repairs",
        "spare_activations",
        "resumed_scrubs",
        "duplicate_alerts",
        "recovery_alerts",
    ):
        assert isinstance(report[key], int) and not isinstance(report[key], bool), key
    for key in (
        "uuid_assembly_clean",
        "limits_restored",
        "budget_ok",
        "triage_ok",
        "adjacency_ok",
        "quorum_ok",
        "checkpoint_ok",
        "accepted",
    ):
        assert isinstance(report[key], bool), key


def test_raidscrub_event_stream_grammar(staged: tuple[Path, Path]) -> None:
    """scrub-events.jsonl records must use documented keys, sequence and event names."""
    root, out = staged
    _apply(root, out)
    events = _events(out)
    assert events, "no campaign events published"
    for index, ev in enumerate(events, start=1):
        assert sorted(ev.keys()) == ["array", "detail", "event", "seq", "uuid"]
        assert ev["seq"] == index
        assert ev["event"] in ALLOWED_EVENTS, ev["event"]
        assert isinstance(ev["detail"], str)
    payload = (out / "scrub-events.jsonl").read_text(encoding="utf-8")
    assert "serial=" not in payload


def test_raidscrub_state_document_shape(staged: tuple[Path, Path]) -> None:
    """array-state.json must carry sorted arrays, empty locks and the model digest."""
    root, out = staged
    _apply(root, out)
    state = _state(out)
    assert sorted(state.keys()) == [
        "arrays",
        "generation",
        "locks_held",
        "model_digest",
        "speed_limit_max",
        "speed_limit_min",
    ]
    uuids = [entry["uuid"] for entry in state["arrays"]]
    assert uuids == sorted(uuids)
    assert set(uuids) == {BOOT_UUID, DATA_UUID, FAST_UUID}
    for entry in state["arrays"]:
        assert sorted(entry.keys()) == [
            "assembled",
            "bitmap",
            "degraded_allowed",
            "level",
            "name",
            "spare_group",
            "uuid",
        ]
    assert state["locks_held"] == []
    assert state["model_digest"] == EXPECTED_DIGEST
    assert isinstance(state["generation"], str) and state["generation"]


# --------------------------------------------------------------------------
# outcome behaviour
# --------------------------------------------------------------------------


def test_raidscrub_host_devices_untouched(staged: tuple[Path, Path]) -> None:
    """Host disk nodes must stay unreferenced and untouched by assembly policy."""
    root, out = staged
    before = {name: Path(name).exists() for name in ("/dev/sda", "/dev/nvme0n1")}
    conf = (root / "etc/mdadm/mdadm.conf").read_text(encoding="utf-8")
    assert "/dev/sd" not in conf and "/dev/nvme" not in conf
    report = _apply(root, out)
    assert report["arrays_known"] == 3
    assert report["uuid_assembly_clean"] is True
    for name, existed in before.items():
        assert Path(name).exists() == existed


def test_raidscrub_dropin_discovery_required(staged: tuple[Path, Path]) -> None:
    """Collapsing the drop-ins back into mdadm.conf must fail acceptance."""
    root, out = staged
    drop = root / "etc/mdadm/mdadm.conf.d"
    main = root / "etc/mdadm/mdadm.conf"
    merged = main.read_text(encoding="utf-8")
    fragments = sorted(drop.glob("*.conf"))
    assert fragments, "no mdadm drop-in fragments were staged"
    for frag in fragments:
        merged += frag.read_text(encoding="utf-8")
        frag.unlink()
    main.write_text(merged, encoding="utf-8")
    report = _apply(root, out)
    assert report["arrays_known"] == 3
    assert report["accepted"] is False


def test_raidscrub_foreign_metadata_excluded(staged: tuple[Path, Path]) -> None:
    """Foreign members must be reported as excluded and never assembled."""
    root, out = staged
    report = _apply(root, out)
    events = _events(out)
    assert any(ev["event"] == "foreign_excluded" for ev in events)
    assert all(
        ev.get("uuid") != FOREIGN_UUID or ev["event"] == "foreign_excluded"
        for ev in events
    )
    assert report["accepted"] is True
    state = _state(out)
    assert all(entry["uuid"] != FOREIGN_UUID for entry in state["arrays"])


def test_raidscrub_parity_degraded_policy_refused(staged: tuple[Path, Path]) -> None:
    """Allowing degraded parity assembly must raise unsafe repairs and fail."""
    root, out = staged
    (root / "etc/default/mdadm").write_text(
        "BOOT_DEGRADED=yes\nRAID5_DEGRADED=allow\n", encoding="utf-8"
    )
    report = _apply(root, out)
    assert report["unsafe_repairs"] >= 1
    assert report["accepted"] is False


def test_raidscrub_budget_consumes_global_ceiling(staged: tuple[Path, Path]) -> None:
    """Per-array ceilings must meet every floor and sum to the restored global maximum."""
    root, out = staged
    budget = _read_budget(root)
    assert set(budget) == set(FLOORS), budget
    for name, floor in FLOORS.items():
        assert budget[name] >= floor, (name, budget[name], floor)
    assert sum(budget.values()) == GLOBAL_MAX
    report = _apply(root, out)
    assert report["budget_ok"] is True
    assert report["limits_restored"] is True
    assert any(ev["event"] == "budget_applied" for ev in _events(out))
    state = _state(out)
    assert state["speed_limit_min"] == 1000
    assert state["speed_limit_max"] == GLOBAL_MAX
    assert (
        root / "var/lib/raid-scrub/state/speed_limit_min"
    ).read_text(encoding="utf-8").strip() == "1000"
    assert (
        root / "var/lib/raid-scrub/state/speed_limit_max"
    ).read_text(encoding="utf-8").strip() == str(GLOBAL_MAX)


def test_raidscrub_budget_unassigned_headroom_rejected(
    staged: tuple[Path, Path],
) -> None:
    """Ceilings equal to the floors leave headroom unassigned and must fail."""
    root, out = staged
    _set_budget(root, 20000, 80000, 60000)
    report = _apply(root, out)
    assert report["budget_ok"] is False
    assert report["accepted"] is False
    assert any(ev["event"] == "budget_rejected" for ev in _events(out))


def test_raidscrub_budget_starved_array_rejected(staged: tuple[Path, Path]) -> None:
    """A budget that hits the global sum while starving an array must fail."""
    root, out = staged
    _set_budget(root, 10000, 110000, 80000)
    report = _apply(root, out)
    assert sum(_read_budget(root).values()) == GLOBAL_MAX
    assert report["budget_ok"] is False
    assert report["accepted"] is False


def test_raidscrub_triage_activates_urgent_group(staged: tuple[Path, Path]) -> None:
    """Exactly one spare from the urgent array's own group must activate."""
    root, out = staged
    report = _apply(root, out)
    assert report["spare_activations"] == 1
    assert report["triage_ok"] is True
    activations = [ev for ev in _events(out) if ev["event"] == "spare_activated"]
    assert len(activations) == 1
    assert activations[0]["array"] == "data5"
    assert "spares/data/" in str(activations[0]["detail"])


def test_raidscrub_triage_without_declaration_rejected(
    staged: tuple[Path, Path],
) -> None:
    """Removing the urgency declaration must withhold every spare."""
    root, out = staged
    (root / "etc/raid-scrub/urgency.conf").unlink()
    report = _apply(root, out)
    assert report["spare_activations"] == 0
    assert report["triage_ok"] is False
    assert report["accepted"] is False
    assert not any(ev["event"] == "spare_activated" for ev in _events(out))


def test_raidscrub_triage_cross_group_spare_rejected(
    staged: tuple[Path, Path],
) -> None:
    """A spare declared outside its own group directory is never eligible."""
    root, out = staged
    (root / "etc/mdadm/spare-groups.conf").write_text(
        "boot=var/lib/raid-scrub/members/spares/boot/spare0.meta\n"
        "data=var/lib/raid-scrub/members/spares/fast/spare0.meta\n"
        "fast=var/lib/raid-scrub/members/spares/fast/spare0.meta\n",
        encoding="utf-8",
    )
    report = _apply(root, out)
    assert report["spare_activations"] == 0
    assert report["triage_ok"] is False
    assert report["accepted"] is False
    assert any(ev["event"] == "spare_withheld" for ev in _events(out))


def test_raidscrub_calendar_days_inside_windows(staged: tuple[Path, Path]) -> None:
    """Each staged timer day must sit inside its published maintenance window."""
    root, out = staged
    days: dict[str, int] = {}
    for name in WINDOWS:
        text = (
            root / f"etc/systemd/system/raid-scrub-{name}.timer"
        ).read_text(encoding="utf-8")
        token = text.split("OnCalendar=*-*-", 1)[1].split(" ", 1)[0]
        assert not token.startswith("0"), f"{name} uses a padded day"
        days[name] = int(token)
    for name, (low, high) in WINDOWS.items():
        assert low <= days[name] <= high, (name, days[name])
    ordered = sorted(days.values())
    for first, second in itertools.pairwise(ordered):
        assert second - first >= 7, ordered
    report = _apply(root, out)
    assert report["concurrent_scrubs_peak"] == 1
    assert report["adjacency_ok"] is True


def test_raidscrub_calendar_padded_day_rejected(staged: tuple[Path, Path]) -> None:
    """A zero-padded OnCalendar day must remove that array's window."""
    root, out = staged
    _set_timer_day(root, "data5", "08")
    report = _apply(root, out)
    assert report["concurrent_scrubs_peak"] != 1
    assert report["accepted"] is False


def test_raidscrub_calendar_crowded_days_rejected(staged: tuple[Path, Path]) -> None:
    """Days inside their windows but closer than a week must fail adjacency."""
    root, out = staged
    _set_timer_day(root, "bootmirror", "7")
    _set_timer_day(root, "data5", "8")
    _set_timer_day(root, "fast10", "15")
    report = _apply(root, out)
    assert report["concurrent_scrubs_peak"] == 1
    assert report["adjacency_ok"] is False
    assert report["accepted"] is False


def test_raidscrub_rebuild_state_skips_scrub(staged: tuple[Path, Path]) -> None:
    """A rebuild sync_action must publish a skip instead of scrubbing."""
    root, out = staged
    (root / "var/lib/raid-scrub/state/fast10/sync_action").write_text(
        "rebuild\n", encoding="utf-8"
    )
    _apply(root, out)
    events = _events(out)
    assert any(
        ev["event"] == "scrub_skipped_rebuild" and ev["array"] == "fast10"
        for ev in events
    )
    assert not any(
        ev["event"] in {"scrub_started", "scrub_resumed"} and ev["array"] == "fast10"
        for ev in events
    )


def test_raidscrub_damaged_checkpoint_blocks_resume(staged: tuple[Path, Path]) -> None:
    """A live journal must resume once and a marked journal must never resume."""
    root, out = staged
    cp = _checkpoint(root)
    assert cp.is_file(), "no live parity checkpoint staged"
    clean = cp.read_text(encoding="utf-8")
    assert int(clean.strip()) > 0
    for path in cp.parent.glob("*.offset"):
        assert "CORRUPT" not in path.read_text(encoding="utf-8"), path.name
    live = _apply(root, out.parent / "cp-live")
    assert live["resumed_scrubs"] == 1
    assert live["checkpoint_ok"] is True
    assert any(
        ev["event"] == "scrub_resumed" and ev["array"] == "data5"
        for ev in _events(out.parent / "cp-live")
    )
    cp.write_text("CORRUPT journal salvaged mid pass\n", encoding="utf-8")
    report = _apply(root, out)
    assert report["checkpoint_ok"] is False
    assert report["resumed_scrubs"] == 0
    assert report["accepted"] is False
    assert any(
        ev["event"] == "checkpoint_rejected" and ev["array"] == "data5"
        for ev in _events(out)
    )
    cp.write_text(clean, encoding="utf-8")
    restored = _apply(root, out.parent / "cp-restored")
    assert restored["checkpoint_ok"] is True
    assert restored["accepted"] is True
    injected = _apply(root, out.parent / "cp-injected", "--corrupt-checkpoint")
    assert injected["checkpoint_ok"] is False
    assert injected["resumed_scrubs"] == 0
    assert injected["accepted"] is False


def test_raidscrub_quorum_permits_parity_repair(staged: tuple[Path, Path]) -> None:
    """Both approvals present must authorize the parity repair with no unsafe count."""
    root, out = staged
    report = _apply(root, out)
    assert report["quorum_ok"] is True
    assert report["unsafe_repairs"] == 0
    assert any(
        ev["event"] == "repair_authorized" and ev["array"] == "data5"
        for ev in _events(out)
    )


def test_raidscrub_quorum_record_absent_rejected(staged: tuple[Path, Path]) -> None:
    """Removing the change-board record must deny repair and fail acceptance."""
    root, out = staged
    quorum = root / "etc/raid-scrub/repair.quorum"
    assert quorum.is_file(), "no change-board record staged"
    quorum.unlink()
    report = _apply(root, out)
    assert report["quorum_ok"] is False
    assert report["unsafe_repairs"] >= 1
    assert report["accepted"] is False
    assert any(ev["event"] == "quorum_denied" for ev in _events(out))


def test_raidscrub_authorization_absent_refuses_repair(
    staged: tuple[Path, Path],
) -> None:
    """Without the array UUID authorization the parity repair must be refused."""
    root, out = staged
    (root / "etc/raid-scrub/repair.authorize").write_text("", encoding="utf-8")
    report = _apply(root, out)
    assert report["quorum_ok"] is False
    assert report["unsafe_repairs"] >= 1
    assert report["accepted"] is False
    assert any(ev["event"] == "repair_refused" for ev in _events(out))


def test_raidscrub_monitor_campaign_never_repairs(staged: tuple[Path, Path]) -> None:
    """Monitor mode must observe every array and repair none."""
    root, out = staged
    report = _apply(root, out, campaign="monitor")
    events = _events(out)
    assert not any(ev["event"] == "repair_authorized" for ev in events)
    assert not any(ev["event"] == "quorum_denied" for ev in events)
    assert report["unsafe_repairs"] == 0
    assert report["quorum_ok"] is True
    assert report["accepted"] is True


def test_raidscrub_read_error_releases_lock(staged: tuple[Path, Path]) -> None:
    """An injected media error must stop the repair and release every lock."""
    root, out = staged
    report = _apply(root, out, "--read-error")
    events = _events(out)
    assert any(ev["event"] == "read_error" for ev in events)
    assert any(ev["event"] == "lock_released" for ev in events)
    assert _state(out)["locks_held"] == []
    locks = root / "var/lib/raid-scrub/locks"
    if locks.exists():
        assert list(locks.glob("*.lock")) == []
    assert report["unsafe_repairs"] == 0
    assert report["limits_restored"] is True


def test_raidscrub_alert_suppression_and_recovery(staged: tuple[Path, Path]) -> None:
    """Degraded alerts must not duplicate and recovery must be announced cleanly."""
    root, out = staged
    notify = (root / "usr/local/lib/raid-scrub/notify.sh").read_text(encoding="utf-8")
    assert "serial=" not in notify
    assert "recovered" in notify
    report = _apply(root, out)
    assert report["duplicate_alerts"] == 0
    assert report["recovery_alerts"] == 1
    assert (root / "var/lib/raid-scrub/alerts/last-state.json").is_file()
    assert any(ev["event"] == "alert_recovery" for ev in _events(out))


# --------------------------------------------------------------------------
# composite
# --------------------------------------------------------------------------


def test_raidscrub_composite_full_acceptance(staged: tuple[Path, Path]) -> None:
    """A correct staged root must publish the exact accepted report and state."""
    root, out = staged
    report = _apply(root, out)
    assert report == ACCEPTED_REPORT
    state = _state(out)
    by_name = {entry["name"]: entry for entry in state["arrays"]}
    assert by_name["bootmirror"]["bitmap"] == "internal"
    assert by_name["data5"]["bitmap"] == "none"
    assert by_name["fast10"]["bitmap"] == "internal"
    assert by_name["bootmirror"]["degraded_allowed"] is True
    assert all(entry["assembled"] is True for entry in state["arrays"])
    assert state["locks_held"] == []


def test_raidscrub_composite_urgent_override_bootmirror(
    staged: tuple[Path, Path],
) -> None:
    """Redirecting triage to the boot mirror must move the activated spare."""
    root, out = staged
    report = _apply(root, out, "--urgent=bootmirror")
    activations = [ev for ev in _events(out) if ev["event"] == "spare_activated"]
    assert len(activations) == 1
    assert activations[0]["array"] == "bootmirror"
    assert activations[0]["uuid"] == BOOT_UUID
    assert "spares/boot/" in str(activations[0]["detail"])
    assert report["spare_activations"] == 1
    assert report["triage_ok"] is True
    assert report["accepted"] is True


def test_raidscrub_composite_relocated_and_renamed(tmp_path: Path) -> None:
    """A relocated root with reordered drop-ins and renamed members must still pass."""
    root = tmp_path / "relocated"
    out = tmp_path / "out-reloc"
    _write_good_root(root)
    drop = root / "etc/mdadm/mdadm.conf.d"
    for index, frag in enumerate(sorted(drop.glob("*.conf"))):
        frag.rename(drop / f"{90 - index * 40}-shuffled.conf")
    members = root / "var/lib/raid-scrub/members/data5"
    for path in sorted(members.glob("*.meta")):
        path.rename(path.with_name(path.stem + "-alias.meta"))
    report = _apply(root, out)
    assert report == ACCEPTED_REPORT
    assert (out / "raid-report.json").is_file()


def test_raidscrub_composite_cascading_faults(staged: tuple[Path, Path]) -> None:
    """Independent faults must each surface in their own field without masking."""
    root, out = staged
    _set_budget(root, 20000, 80000, 60000)
    (root / "etc/raid-scrub/repair.quorum").unlink()
    _set_timer_day(root, "fast10", "015")
    report = _apply(root, out)
    assert report["budget_ok"] is False
    assert report["quorum_ok"] is False
    assert report["concurrent_scrubs_peak"] != 1
    assert report["arrays_known"] == 3
    assert report["uuid_assembly_clean"] is True
    assert report["triage_ok"] is True
    assert report["checkpoint_ok"] is True
    assert report["accepted"] is False


# --------------------------------------------------------------------------
# metamorphic
# --------------------------------------------------------------------------


def test_raidscrub_metamorphic_uuid_case_equivalence(staged: tuple[Path, Path]) -> None:
    """Uppercase UUID tokens must normalize and keep acceptance unchanged."""
    root, out = staged
    baseline = _apply(root, out)
    target = None
    for frag in sorted((root / "etc/mdadm/mdadm.conf.d").glob("*.conf")):
        text = frag.read_text(encoding="utf-8")
        if DATA_UUID in text:
            target = frag
            frag.write_text(text.replace(DATA_UUID, DATA_UUID.upper()), encoding="utf-8")
            break
    assert target is not None, "parity drop-in not found"
    report = _apply(root, out.parent / "upper")
    assert report == baseline == ACCEPTED_REPORT


def test_raidscrub_metamorphic_repeat_apply_identical_bytes(
    staged: tuple[Path, Path],
) -> None:
    """Repeating an apply must republish byte-identical report and state documents."""
    root, out = staged
    _apply(root, out)
    first_report = (out / "raid-report.json").read_bytes()
    first_state = (out / "array-state.json").read_bytes()
    _apply(root, out)
    assert (out / "raid-report.json").read_bytes() == first_report
    assert (out / "array-state.json").read_bytes() == first_state
    mon = out.parent / "monitor"
    _apply(root, mon, campaign="monitor")
    first_mon = (mon / "raid-report.json").read_bytes()
    _apply(root, mon, campaign="monitor")
    assert (mon / "raid-report.json").read_bytes() == first_mon


def test_raidscrub_metamorphic_budget_reallocation_equivalent(
    staged: tuple[Path, Path],
) -> None:
    """Any distribution meeting the floors and the global sum must behave the same."""
    root, out = staged
    baseline = _apply(root, out)
    assert baseline == ACCEPTED_REPORT
    _set_budget(root, 30000, 90000, 80000)
    shifted = _apply(root, out.parent / "realloc")
    assert shifted == ACCEPTED_REPORT
    _set_budget(root, 40000, 80000, 80000)
    again = _apply(root, out.parent / "realloc2")
    assert again == ACCEPTED_REPORT


def test_raidscrub_metamorphic_calendar_shift_equivalent(
    staged: tuple[Path, Path],
) -> None:
    """Shifting every scrub day inside its window must not change acceptance."""
    root, out = staged
    _set_timer_day(root, "bootmirror", "3")
    _set_timer_day(root, "data5", "10")
    _set_timer_day(root, "fast10", "17")
    report = _apply(root, out)
    assert report == ACCEPTED_REPORT
    _set_timer_day(root, "bootmirror", "1")
    _set_timer_day(root, "data5", "14")
    _set_timer_day(root, "fast10", "28")
    wide = _apply(root, out.parent / "wide")
    assert wide == ACCEPTED_REPORT


def test_raidscrub_metamorphic_epoch_record_variants(staged: tuple[Path, Path]) -> None:
    """An explicit epoch record must authorize only the epoch it names."""
    root, out = staged
    (root / "etc/raid-scrub/repair.quorum").write_text("epoch=5\n", encoding="utf-8")
    matched = _apply(root, out, epoch="5")
    assert matched["quorum_ok"] is True
    assert matched["unsafe_repairs"] == 0
    assert matched["accepted"] is True
    unmatched = _apply(root, out.parent / "epoch-default")
    assert unmatched["quorum_ok"] is False
    assert unmatched["unsafe_repairs"] >= 1
    assert unmatched["accepted"] is False
    (root / "etc/raid-scrub/repair.quorum").write_text(
        "epoch=5\nepoch=*\n", encoding="utf-8"
    )
    wildcard = _apply(root, out.parent / "epoch-wildcard", epoch="9")
    assert wildcard["quorum_ok"] is True
    assert wildcard["accepted"] is True


def test_raidscrub_metamorphic_threshold_raise_still_needs_quorum(
    staged: tuple[Path, Path],
) -> None:
    """Raising the threshold removes the repair but not the approval requirement."""
    root, out = staged
    relaxed = _apply(root, out, threshold=20)
    assert relaxed["unsafe_repairs"] == 0
    assert relaxed["accepted"] is True
    assert not any(ev["event"] == "repair_authorized" for ev in _events(out))
    (root / "etc/raid-scrub/repair.quorum").write_text("", encoding="utf-8")
    stripped = _apply(root, out.parent / "relaxed-noquorum", threshold=20)
    assert stripped["unsafe_repairs"] == 0
    assert stripped["quorum_ok"] is False
    assert stripped["accepted"] is False
