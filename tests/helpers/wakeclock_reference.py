from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_units(unit_dir: Path) -> list[dict[str, object]]:
    units = [json.loads(path.read_text()) for path in unit_dir.glob("*.timer.json")]
    return sorted(units, key=lambda item: str(item["unit_id"]))


def read_trace(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def occurrence(unit: dict[str, object], instant: datetime) -> dict[str, object]:
    local = instant.astimezone(ZoneInfo(str(unit["timezone"])))
    offset = int(local.utcoffset().total_seconds())
    local_text = local.strftime("%Y-%m-%dT%H:%M:%S")
    utc_text = format_time(instant)
    occurrence_id = f'{unit["unit_id"]}|{local_text}|{offset}|{utc_text}'
    seed = (
        f'{unit["unit_id"]}\n{occurrence_id}\n{unit["salt"]}\n'.encode()
    )
    first_eight = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big")
    delay = first_eight % (int(unit["random_delay_sec"]) + 1)
    return {
        "unit_id": unit["unit_id"],
        "occurrence_id": occurrence_id,
        "scheduled_local": local_text,
        "scheduled_utc": utc_text,
        "offset_sec": offset,
        "delayed_utc": format_time(instant + timedelta(seconds=delay)),
        "accuracy_sec": unit["accuracy_sec"],
        "priority": unit["priority"],
        "depends_on": list(unit["depends_on"]),
    }


def enumerate_occurrences(
    units: list[dict[str, object]],
    start: datetime,
    end: datetime,
    event_time: datetime,
) -> list[dict[str, object]]:
    instant = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    result: list[dict[str, object]] = []
    while instant <= end:
        for unit in units:
            if not unit["enabled"]:
                continue
            local = instant.astimezone(ZoneInfo(str(unit["timezone"])))
            go_weekday = (local.weekday() + 1) % 7
            if (
                local.hour != unit["hour"]
                or local.minute != unit["minute"]
                or go_weekday not in unit["weekdays"]
            ):
                continue
            if not unit["persistent"] and instant != event_time:
                continue
            result.append(occurrence(unit, instant))
        instant += timedelta(minutes=1)
    return sorted(
        result,
        key=lambda item: (
            str(item["scheduled_utc"]),
            str(item["unit_id"]),
            str(item["occurrence_id"]),
        ),
    )


def group_ids(group: list[dict[str, object]]) -> tuple[str, str, str, list[str]]:
    ids = sorted(str(item["occurrence_id"]) for item in group)
    group_id = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    activation_id = hashlib.sha256(f"activation\n{group_id}\n".encode()).hexdigest()
    effective = min(str(item["delayed_utc"]) for item in group)
    return group_id, activation_id, effective, ids


def coalesce(ready: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    items = sorted(
        ready,
        key=lambda item: (
            str(item["delayed_utc"]),
            str(item["unit_id"]),
            str(item["occurrence_id"]),
        ),
    )
    groups: list[list[dict[str, object]]] = []
    deadline: datetime | None = None
    for item in items:
        when = parse_time(str(item["delayed_utc"]))
        window_end = when + timedelta(seconds=int(item["accuracy_sec"]))
        if not groups or deadline is None or when > deadline:
            groups.append([item])
            deadline = window_end
        else:
            groups[-1].append(item)
            deadline = min(deadline, window_end)
    return groups


def dependency_order(
    group: list[dict[str, object]], state: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, str]], list[dict[str, str]]]:
    by_unit: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(group):
        by_unit[str(item["unit_id"])].append(index)
    skipped: set[int] = set()
    history = state["last_activation"]
    for index, item in enumerate(group):
        for dependency in item["depends_on"]:
            if not by_unit[str(dependency)] and not history.get(str(dependency), ""):
                skipped.add(index)
                break
    changed = True
    while changed:
        changed = False
        for index, item in enumerate(group):
            if index in skipped:
                continue
            for dependency in item["depends_on"]:
                if any(dep_index in skipped for dep_index in by_unit[str(dependency)]):
                    skipped.add(index)
                    changed = True
                    break

    indegree = [0] * len(group)
    outgoing: dict[int, list[int]] = defaultdict(list)
    for index, item in enumerate(group):
        if index in skipped:
            continue
        for dependency in item["depends_on"]:
            for dependency_index in by_unit[str(dependency)]:
                if dependency_index in skipped or dependency_index == index:
                    continue
                indegree[index] += 1
                outgoing[dependency_index].append(index)

    ordered: list[dict[str, object]] = []
    used: set[int] = set()
    while True:
        eligible = [
            index
            for index in range(len(group))
            if index not in skipped and index not in used and indegree[index] == 0
        ]
        if not eligible:
            break
        index = min(
            eligible,
            key=lambda candidate: (
                -int(group[candidate]["priority"]),
                str(group[candidate]["unit_id"]),
                str(group[candidate]["occurrence_id"]),
            ),
        )
        used.add(index)
        ordered.append(group[index])
        for dependent in outgoing[index]:
            indegree[dependent] -= 1

    decisions: list[dict[str, str]] = []
    skips: list[dict[str, str]] = []
    for index, item in enumerate(group):
        occurrence_id = str(item["occurrence_id"])
        unit_id = str(item["unit_id"])
        if index in skipped:
            decisions.append(
                {
                    "unit_id": unit_id,
                    "occurrence_id": occurrence_id,
                    "decision": "skipped_missing_prerequisite",
                }
            )
            skips.append(
                {
                    "occurrence_id": occurrence_id,
                    "unit_id": unit_id,
                    "reason": "missing_prerequisite",
                }
            )
            continue
        in_group = any(by_unit[str(dep)] for dep in item["depends_on"])
        historical = any(not by_unit[str(dep)] for dep in item["depends_on"])
        decision = "ready"
        if in_group:
            decision = "ordered_after_group_dependency"
        elif historical:
            decision = "satisfied_by_history"
        decisions.append(
            {
                "unit_id": unit_id,
                "occurrence_id": occurrence_id,
                "decision": decision,
            }
        )
    decisions.sort(key=lambda item: (item["occurrence_id"], item["unit_id"]))
    skips.sort(key=lambda item: (item["occurrence_id"], item["unit_id"]))
    return ordered, decisions, skips


def consume(
    state: dict[str, object], unit_id: str, occurrence_id: str, activation_id: str
) -> None:
    state["pending"] = [
        item for item in state["pending"] if item["occurrence_id"] != occurrence_id
    ]
    state["cursors"][unit_id] = occurrence_id
    if activation_id:
        state["last_activation"][unit_id] = activation_id


def recover(
    state_dir: Path,
    state: dict[str, object],
    journal: list[dict[str, object]],
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    order: list[str] = []
    by_id: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in journal:
        activation_id = str(record["activation_id"])
        if activation_id not in by_id:
            order.append(activation_id)
        by_id[activation_id].append(record)
    decisions: list[dict[str, str]] = []
    kept: list[dict[str, object]] = []
    for activation_id in order:
        records = by_id[activation_id]
        if len(records) == 1:
            decisions.append(
                {"activation_id": activation_id, "decision": "discarded_prepare"}
            )
            continue
        spool = json.loads(
            (state_dir / "spool" / f"{activation_id}.json").read_text()
        )
        kept.extend(records)
        base = records[0]
        if len(records) == 2:
            kept.append(
                {
                    "activation_id": activation_id,
                    "phase": "commit",
                    "group_id": base["group_id"],
                    "occurrence_ids": list(base["occurrence_ids"]),
                }
            )
            state["committed_ids"].append(activation_id)
            for item in list(state["pending"]):
                if item["occurrence_id"] in base["occurrence_ids"]:
                    consume(state, str(item["unit_id"]), str(item["occurrence_id"]), "")
            for unit_id in spool["unit_ids"]:
                state["last_activation"][unit_id] = activation_id
            decisions.append(
                {"activation_id": activation_id, "decision": "completed_spool"}
            )
        elif activation_id not in state["committed_ids"]:
            state["committed_ids"].append(activation_id)
            for item in list(state["pending"]):
                if item["occurrence_id"] in base["occurrence_ids"]:
                    consume(state, str(item["unit_id"]), str(item["occurrence_id"]), "")
            for unit_id in spool["unit_ids"]:
                state["last_activation"][unit_id] = activation_id
            decisions.append(
                {"activation_id": activation_id, "decision": "replayed_commit"}
            )
    state["committed_ids"] = sorted(set(state["committed_ids"]))
    decisions.sort(key=lambda item: item["activation_id"])
    return decisions, kept


def canonical_state(state: dict[str, object]) -> dict[str, object]:
    pending = sorted(
        state["pending"],
        key=lambda item: (
            str(item["delayed_utc"]),
            str(item["unit_id"]),
            str(item["occurrence_id"]),
        ),
    )
    return {
        "schema_version": state["schema_version"],
        "trace_seq": state["trace_seq"],
        "clock_utc": state["clock_utc"],
        "high_water_utc": state["high_water_utc"],
        "boot_id": state["boot_id"],
        "pending": pending,
        "committed_ids": sorted(set(state["committed_ids"])),
        "last_activation": dict(sorted(state["last_activation"].items())),
        "cursors": dict(sorted(state["cursors"].items())),
    }


def reconcile(
    unit_dir: Path,
    state_dir: Path,
    trace_path: Path,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]], dict[str, dict[str, object]]]:
    units = read_units(unit_dir)
    state = json.loads((state_dir / "snapshot.json").read_text())
    journal = [
        json.loads(line)
        for line in (state_dir / "journal.jsonl").read_text().splitlines()
        if line.strip()
    ]
    recovered, journal = recover(state_dir, state, journal)
    report: dict[str, object] = {
        "schema_version": "wakeclock.reconcile.v1",
        "trace_seq": state["trace_seq"],
        "recovered": recovered,
        "activations": [],
        "skipped": [],
        "coalescing_groups": [],
        "dependency_decisions": [],
        "final_cursors": {},
        "state_digest": "",
    }
    spools: dict[str, dict[str, object]] = {}
    seen = {item["occurrence_id"] for item in state["pending"]}
    caps = {str(unit["unit_id"]): int(unit["catch_up_cap"]) for unit in units}

    for event in read_trace(trace_path):
        if int(event["seq"]) <= int(state["trace_seq"]):
            continue
        instant = parse_time(str(event["utc"]))
        high_water = parse_time(str(state["high_water_utc"]))
        if instant > high_water:
            for item in enumerate_occurrences(units, high_water, instant, instant):
                if item["occurrence_id"] not in seen:
                    state["pending"].append(item)
                    seen.add(item["occurrence_id"])
            state["high_water_utc"] = format_time(instant)
        state["clock_utc"] = format_time(instant)
        state["trace_seq"] = event["seq"]
        if event["kind"] == "boot":
            state["boot_id"] = event["boot_id"]

        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for item in state["pending"]:
            grouped[str(item["unit_id"])].append(item)
        dropped: set[str] = set()
        for unit_id in sorted(grouped):
            items = sorted(
                grouped[unit_id],
                key=lambda item: (str(item["scheduled_utc"]), str(item["occurrence_id"])),
            )
            while len(items) > caps[unit_id]:
                item = items.pop(0)
                occurrence_id = str(item["occurrence_id"])
                dropped.add(occurrence_id)
                seen.discard(occurrence_id)
                state["cursors"][unit_id] = occurrence_id
                report["skipped"].append(
                    {
                        "occurrence_id": occurrence_id,
                        "unit_id": unit_id,
                        "reason": "catch_up_cap",
                    }
                )
                report["dependency_decisions"].append(
                    {
                        "unit_id": unit_id,
                        "occurrence_id": occurrence_id,
                        "decision": "skipped_catch_up_cap",
                    }
                )
        state["pending"] = [
            item for item in state["pending"] if item["occurrence_id"] not in dropped
        ]

        ready = [
            item
            for item in state["pending"]
            if parse_time(str(item["delayed_utc"])) <= instant
        ]
        for group in coalesce(ready):
            group_id, activation_id, effective, all_ids = group_ids(group)
            report["coalescing_groups"].append(
                {
                    "group_id": group_id,
                    "effective_utc": effective,
                    "occurrence_ids": all_ids,
                }
            )
            ordered, decisions, skips = dependency_order(group, state)
            report["dependency_decisions"].extend(decisions)
            report["skipped"].extend(skips)
            for item in skips:
                consume(state, item["unit_id"], item["occurrence_id"], "")
            if not ordered:
                continue
            unit_ids = [str(item["unit_id"]) for item in ordered]
            occurrence_ids = [str(item["occurrence_id"]) for item in ordered]
            activation = {
                "activation_id": activation_id,
                "group_id": group_id,
                "effective_utc": effective,
                "unit_ids": unit_ids,
                "occurrence_ids": occurrence_ids,
            }
            report["activations"].append(activation)
            for phase in ("prepare", "spool", "commit"):
                journal.append(
                    {
                        "activation_id": activation_id,
                        "phase": phase,
                        "group_id": group_id,
                        "occurrence_ids": all_ids,
                    }
                )
            spools[activation_id] = activation
            state["committed_ids"].append(activation_id)
            for item in ordered:
                consume(
                    state,
                    str(item["unit_id"]),
                    str(item["occurrence_id"]),
                    activation_id,
                )
        report["trace_seq"] = state["trace_seq"]

    state = canonical_state(state)
    compact = json.dumps(state, separators=(",", ":"), ensure_ascii=False)
    report["final_cursors"] = dict(sorted(state["cursors"].items()))
    report["state_digest"] = hashlib.sha256(compact.encode()).hexdigest()
    return report, state, journal, spools
