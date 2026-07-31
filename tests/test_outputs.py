import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

BINARY = Path("/workspace/bin/systemd-window-plan")
SOURCE_DIR = Path("/workspace/cmd/systemd-window-plan")
SOURCE = SOURCE_DIR / "main.go"
PUBLIC_INPUT = Path("/workspace/task_file/window_request.json")
PUBLIC_OUTPUT = Path("/workspace/output/window_plan.json")
PUBLIC_SHA256 = "78c37f5bc18de9110fc00f2f2cf0d15f8b7d25b6f2fda07025dd0898a3a43040"

REASON_ORDER = [
    "changed_restart",
    "changed_reload",
    "reload_escalated",
    "requested_start",
    "part_of",
    "propagated_reload",
    "required_dependency",
    "wanted_dependency",
    "requires_mounts_for",
    "conflict_stop",
    "inactive_changed",
    "protected",
    "not_selected",
]


def ordered_reasons(reasons):
    return [reason for reason in REASON_ORDER if reason in reasons]


def source_rank(source):
    return {"vendor": 1, "runtime": 2, "admin": 3}.get(source, 0)


def default_directives():
    return {
        "requires": [],
        "wants": [],
        "after": [],
        "before": [],
        "conflicts": [],
        "part_of": [],
        "propagates_reload_to": [],
        "requires_mounts_for": [],
        "condition_paths": [],
        "reloadable": False,
        "refuse_manual_start": False,
        "start_sec": 1,
        "stop_sec": 1,
        "reload_sec": 1,
    }


LIST_DIRECTIVES = {
    "requires",
    "wants",
    "after",
    "before",
    "conflicts",
    "part_of",
    "propagates_reload_to",
    "requires_mounts_for",
    "condition_paths",
}


class Reference:
    def __init__(self, raw):
        self.raw = copy.deepcopy(raw)
        self.defs, self.active_paths = self.materialize(raw["fragments"])
        self.runtime = {row["unit"]: row for row in raw["runtime"]}
        self.paths = {row["path"]: row for row in raw["paths"]}
        self.protected = set(raw["maintenance"]["protected_units"])
        self.requested = set(raw["maintenance"]["request_units"])
        self.conflicts = {}
        self.part_of_reverse = {}
        self.roots = []
        self.root_by_unit = {}
        self.inactive_changed = set()
        self.warnings = []
        self.daemon_reloaded = False
        self.build_relations()
        self.build_changes()

    def materialize(self, fragments):
        bases = {}
        dropins = {}
        for frag in fragments:
            if frag["kind"] == "base":
                old = bases.get(frag["unit"])
                if old is None or self.better_fragment(frag, old):
                    bases[frag["unit"]] = frag
            if frag["kind"] == "dropin":
                key = (frag["unit"], frag["dropin"])
                old = dropins.get(key)
                if old is None or self.better_fragment(frag, old):
                    dropins[key] = frag

        by_unit = {}
        for frag in dropins.values():
            by_unit.setdefault(frag["unit"], []).append(frag)
        for rows in by_unit.values():
            rows.sort(key=lambda item: (item["dropin"], item["path"]))

        defs = {}
        active_paths = set()
        for unit, base_frag in bases.items():
            directives = default_directives()
            self.apply_directives(directives, base_frag)
            active_paths.add(base_frag["path"])
            for dropin in by_unit.get(unit, []):
                self.apply_directives(directives, dropin)
                active_paths.add(dropin["path"])
            for name in LIST_DIRECTIVES:
                directives[name] = sorted({value for value in directives[name] if value})
            defs[unit] = {
                "name": unit,
                "base_path": base_frag["path"],
                "directives": directives,
            }
        return defs, active_paths

    @staticmethod
    def better_fragment(left, right):
        if source_rank(left["source"]) != source_rank(right["source"]):
            return source_rank(left["source"]) > source_rank(right["source"])
        return left["path"] < right["path"]

    @staticmethod
    def apply_directives(current, frag):
        for name in sorted(frag.get("reset", [])):
            if name in LIST_DIRECTIVES:
                current[name] = []
        directives = frag.get("directives") or {}
        for name in LIST_DIRECTIVES:
            current[name].extend(directives.get(name, []))
        for name in (
            "reloadable",
            "refuse_manual_start",
            "start_sec",
            "stop_sec",
            "reload_sec",
        ):
            if name in directives:
                current[name] = directives[name]

    def build_relations(self):
        for unit, definition in self.defs.items():
            for other in definition["directives"]["conflicts"]:
                self.conflicts.setdefault(unit, set()).add(other)
                self.conflicts.setdefault(other, set()).add(unit)
            for parent in definition["directives"]["part_of"]:
                self.part_of_reverse.setdefault(parent, []).append(unit)
        for children in self.part_of_reverse.values():
            children.sort()

    def build_changes(self):
        groups = {}
        for chg in self.raw["changes"]:
            if chg["path"] not in self.active_paths:
                self.warnings.append(
                    {"code": "shadowed_change", "unit": chg["unit"], "path": chg["path"]}
                )
                continue
            self.daemon_reloaded = True
            if chg["impact"] == "none":
                continue
            group = groups.setdefault(
                chg["unit"],
                {"unit": chg["unit"], "priority": 0, "restart": False, "reload": False},
            )
            group["priority"] += chg["priority"]
            if chg["impact"] == "restart":
                group["restart"] = True
            if chg["impact"] == "reload":
                group["reload"] = True
        self.warnings.sort(key=lambda row: (row["unit"], row["path"], row["code"]))

        for unit in sorted(groups):
            group = groups[unit]
            reasons = []
            if group["restart"]:
                reasons.append("changed_restart")
            if group["reload"]:
                reasons.append("changed_reload")
            action = "restart" if group["restart"] else "reload"
            if not self.initial_active(unit):
                if unit in self.requested:
                    action = "start"
                    reasons.append("requested_start")
                else:
                    self.inactive_changed.add(unit)
                    continue
            blocked = False
            if unit in self.protected and action in {"restart", "start"}:
                blocked = True
            if unit in self.protected and action == "reload":
                definition = self.defs.get(unit)
                if definition is not None and not definition["directives"]["reloadable"]:
                    blocked = True
            root = {
                "unit": unit,
                "action": action,
                "priority": group["priority"],
                "reasons": ordered_reasons(set(reasons)),
                "blocked": blocked,
            }
            self.root_by_unit[unit] = root
            self.roots.append(root)

    def solve(self):
        best = None

        def visit(idx, actions):
            nonlocal best
            if idx == len(self.roots):
                for plan in self.expand_wants(actions, set()):
                    candidate = self.evaluate(plan)
                    if candidate is None:
                        continue
                    if best is None or self.better(candidate, best):
                        best = candidate
                return
            visit(idx + 1, self.clone_actions(actions))
            root = self.roots[idx]
            if root["blocked"]:
                return
            included = self.clone_actions(actions)
            if self.add_action(included, root["unit"], root["action"], root["reasons"]):
                visit(idx + 1, included)

        visit(0, {})
        if best is None:
            best = self.evaluate({})
        return best["report"]

    @staticmethod
    def better(left, right):
        lo = left["report"]["objective"]
        ro = right["report"]["objective"]
        key_left = (
            -lo["applied_priority"],
            -lo["applied_units"],
            -lo["final_active_units"],
            lo["elapsed_sec"],
            lo["stopped_active_units"],
            left["signature"],
        )
        key_right = (
            -ro["applied_priority"],
            -ro["applied_units"],
            -ro["final_active_units"],
            ro["elapsed_sec"],
            ro["stopped_active_units"],
            right["signature"],
        )
        return key_left < key_right

    @staticmethod
    def clone_actions(actions):
        return {
            unit: {"kind": row["kind"], "reasons": set(row["reasons"])}
            for unit, row in actions.items()
        }

    def expand_wants(self, seed, excluded):
        closed = self.close_mandatory(self.clone_actions(seed))
        if closed is None:
            return []
        wants = self.want_candidates(closed, excluded)
        if not wants:
            return [closed]
        want = wants[0]
        skip_excluded = set(excluded)
        skip_excluded.add(want)
        out = self.expand_wants(closed, skip_excluded)

        included = self.clone_actions(closed)
        if self.add_action(included, want, "start", ["wanted_dependency"]):
            out.extend(self.expand_wants(included, excluded))
        return out

    def want_candidates(self, actions, excluded):
        candidates = set()
        for unit in sorted(actions):
            if actions[unit]["kind"] == "stop":
                continue
            definition = self.defs.get(unit)
            if not definition:
                continue
            for wanted in definition["directives"]["wants"]:
                if wanted in excluded or wanted in actions or self.is_active_after(wanted, actions):
                    continue
                if not self.startable(wanted) or wanted in self.protected:
                    continue
                candidates.add(wanted)
        return sorted(candidates)

    def close_mandatory(self, seed):
        actions = self.clone_actions(seed)
        changed = True
        while changed:
            changed = False
            for unit in sorted(actions):
                if actions[unit]["kind"] != "reload":
                    continue
                definition = self.defs.get(unit)
                if definition is None:
                    return None
                if not definition["directives"]["reloadable"]:
                    if unit in self.protected:
                        return None
                    if self.add_action(actions, unit, "restart", ["reload_escalated"]):
                        changed = True
                    else:
                        return None
            for unit in sorted(actions):
                kind = actions[unit]["kind"]
                if kind == "restart":
                    for child in self.part_of_reverse.get(unit, []):
                        if self.initial_active(child) and self.add_action(
                            actions, child, "restart", ["part_of"]
                        ):
                            changed = True
                if kind == "reload":
                    definition = self.defs.get(unit)
                    if definition is None:
                        return None
                    for target in definition["directives"]["propagates_reload_to"]:
                        if self.initial_active(target) and self.add_action(
                            actions, target, "reload", ["propagated_reload"]
                        ):
                            changed = True
            for unit in sorted(actions):
                if actions[unit]["kind"] not in {"start", "restart"}:
                    continue
                definition = self.defs.get(unit)
                if definition is None:
                    return None
                for path in definition["directives"]["requires_mounts_for"]:
                    if self.path_exists_after(path, actions):
                        continue
                    info = self.paths.get(path)
                    if not info or not info["mount_unit"]:
                        return None
                    mount = info["mount_unit"]
                    if not self.is_active_after(mount, actions):
                        if not self.startable(mount) or mount in self.protected:
                            return None
                        if self.add_action(actions, mount, "start", ["requires_mounts_for"]):
                            changed = True
                for required in definition["directives"]["requires"]:
                    if self.is_active_after(required, actions):
                        continue
                    if not self.startable(required) or required in self.protected:
                        return None
                    if self.add_action(actions, required, "start", ["required_dependency"]):
                        changed = True
            for unit in sorted(actions):
                if actions[unit]["kind"] not in {"start", "restart"}:
                    continue
                for conflict in sorted(self.conflicts.get(unit, set())):
                    if not self.initial_active(conflict):
                        continue
                    existing = actions.get(conflict)
                    if existing is not None:
                        if existing["kind"] == "stop":
                            continue
                        return None
                    if conflict in self.protected:
                        return None
                    if self.add_action(actions, conflict, "stop", ["conflict_stop"]):
                        changed = True
        for unit in sorted(actions):
            if actions[unit]["kind"] not in {"start", "restart"}:
                continue
            for path in self.defs[unit]["directives"]["condition_paths"]:
                if not self.path_exists_after(path, actions):
                    return None
        return actions

    def add_action(self, actions, unit, kind, reasons):
        if kind in {"start", "restart"} and (
            unit in self.protected or not self.startable(unit)
        ):
            return False
        if kind == "reload" and unit not in self.defs:
            return False
        existing = actions.get(unit)
        if existing is None:
            actions[unit] = {"kind": kind, "reasons": set(reasons)}
            return True
        if existing["kind"] == "stop" and kind != "stop":
            return False
        if existing["kind"] != "stop" and kind == "stop":
            return False
        changed = False
        if kind != "stop" and self.action_rank(kind) > self.action_rank(existing["kind"]):
            existing["kind"] = kind
            changed = True
        before = len(existing["reasons"])
        existing["reasons"].update(reasons)
        return changed or len(existing["reasons"]) != before

    @staticmethod
    def action_rank(kind):
        return {"start": 1, "reload": 2, "restart": 3}.get(kind, 0)

    def evaluate(self, raw_actions):
        actions = self.close_mandatory(self.clone_actions(raw_actions))
        if actions is None:
            return None
        applied_roots = set()
        applied_priority = 0
        applied_units = 0
        for unit, root in self.root_by_unit.items():
            action = actions.get(unit)
            if action and self.root_satisfied(root["action"], action["kind"]):
                applied_roots.add(unit)
                applied_priority += root["priority"]
                applied_units += 1
                action["reasons"].update(root["reasons"])

        operations_and_signature = self.operations(actions)
        if operations_and_signature is None:
            return None
        operations, signature = operations_and_signature
        elapsed = sum(op["duration_sec"] for op in operations)
        stopped_active = sum(
            1 for op in operations if op["action"] == "stop" and self.initial_active(op["unit"])
        )
        mount_starts = sum(
            1
            for op in operations
            if op["action"] in {"start", "restart"} and op["unit"].endswith(".mount")
        )
        maintenance = self.raw["maintenance"]
        if elapsed > maintenance["deadline_sec"]:
            return None
        if stopped_active > maintenance["max_stopped_active"]:
            return None
        if mount_starts > maintenance["mount_start_limit"]:
            return None

        report = {
            "daemon_reloaded": self.daemon_reloaded,
            "objective": {
                "applied_priority": applied_priority,
                "applied_units": applied_units,
                "final_active_units": self.final_active_count(actions),
                "elapsed_sec": elapsed,
                "stopped_active_units": stopped_active,
            },
            "operations": operations,
            "units": self.unit_rows(actions, applied_roots),
            "warnings": copy.deepcopy(self.warnings),
        }
        return {"report": report, "signature": signature}

    @staticmethod
    def root_satisfied(root_action, actual):
        if root_action == "restart":
            return actual == "restart"
        if root_action == "reload":
            return actual in {"reload", "restart"}
        if root_action == "start":
            return actual in {"start", "restart"}
        return False

    def operations(self, actions):
        operations = []
        signature = []
        step = 1
        if self.daemon_reloaded:
            operations.append(
                {
                    "step": step,
                    "action": "daemon-reload",
                    "unit": "",
                    "duration_sec": self.raw["maintenance"]["daemon_reload_sec"],
                    "reasons": ["active_change"],
                }
            )
            signature.append("daemon-reload:")
            step += 1

        for unit in sorted(unit for unit, row in actions.items() if row["kind"] == "stop"):
            operations.append(
                {
                    "step": step,
                    "action": "stop",
                    "unit": unit,
                    "duration_sec": self.duration(unit, "stop"),
                    "reasons": ordered_reasons(actions[unit]["reasons"]),
                }
            )
            signature.append(f"stop:{unit}")
            step += 1

        ordered = self.topological_actions(actions)
        if ordered is None:
            return None
        for unit in ordered:
            kind = actions[unit]["kind"]
            operations.append(
                {
                    "step": step,
                    "action": kind,
                    "unit": unit,
                    "duration_sec": self.duration(unit, kind),
                    "reasons": ordered_reasons(actions[unit]["reasons"]),
                }
            )
            signature.append(f"{kind}:{unit}")
            step += 1
        return operations, signature

    def topological_actions(self, actions):
        nodes = {unit for unit, row in actions.items() if row["kind"] != "stop"}
        edges = {unit: set() for unit in nodes}
        indegree = dict.fromkeys(nodes, 0)

        def add_edge(before, after):
            if before not in nodes or after not in nodes or before == after:
                return
            if after not in edges[before]:
                edges[before].add(after)
                indegree[after] += 1

        for unit in nodes:
            definition = self.defs.get(unit)
            if definition is None:
                return None
            directives = definition["directives"]
            for after in directives["after"]:
                add_edge(after, unit)
            for before in directives["before"]:
                add_edge(unit, before)
            for required in directives["requires"]:
                add_edge(required, unit)
            for path in directives["requires_mounts_for"]:
                info = self.paths.get(path)
                if info and info["mount_unit"]:
                    add_edge(info["mount_unit"], unit)
            for target in directives["propagates_reload_to"]:
                add_edge(unit, target)

        ready = sorted(unit for unit, degree in indegree.items() if degree == 0)
        out = []
        while ready:
            unit = ready.pop(0)
            out.append(unit)
            for nxt in sorted(edges[unit]):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
                    ready.sort()
        if len(out) != len(nodes):
            return None
        return out

    def duration(self, unit, kind):
        if kind == "daemon-reload":
            return self.raw["maintenance"]["daemon_reload_sec"]
        directives = self.defs[unit]["directives"]
        if kind == "start":
            return directives["start_sec"]
        if kind == "stop":
            return directives["stop_sec"]
        if kind == "reload":
            return directives["reload_sec"]
        if kind == "restart":
            return directives["stop_sec"] + directives["start_sec"]
        return 0

    def unit_rows(self, actions, applied_roots):
        names = set(actions) | set(self.root_by_unit) | set(self.inactive_changed)
        rows = []
        for unit in sorted(names):
            action = actions.get(unit)
            if action is not None:
                reasons = set(action["reasons"])
                root = self.root_by_unit.get(unit)
                if root and unit not in applied_roots and not root["blocked"]:
                    reasons.add("not_selected")
                rows.append(
                    {
                        "name": unit,
                        "planned_action": action["kind"],
                        "applied_change": unit in applied_roots,
                        "final_state": self.final_state(unit, actions),
                        "reasons": ordered_reasons(reasons),
                    }
                )
                continue
            root = self.root_by_unit.get(unit)
            if root:
                if root["blocked"]:
                    rows.append(
                        {
                            "name": unit,
                            "planned_action": "unchanged",
                            "applied_change": False,
                            "final_state": self.initial_final_state(unit),
                            "reasons": ["protected"],
                        }
                    )
                else:
                    rows.append(
                        {
                            "name": unit,
                            "planned_action": "deferred",
                            "applied_change": False,
                            "final_state": self.initial_final_state(unit),
                            "reasons": ["not_selected"],
                        }
                    )
                continue
            rows.append(
                {
                    "name": unit,
                    "planned_action": "unchanged",
                    "applied_change": False,
                    "final_state": self.initial_final_state(unit),
                    "reasons": ["inactive_changed"],
                }
            )
        return rows

    def final_active_count(self, actions):
        units = set(self.defs) | set(self.runtime)
        return sum(1 for unit in units if self.final_state(unit, actions) == "active")

    def final_state(self, unit, actions):
        action = actions.get(unit)
        if action:
            if action["kind"] == "stop":
                return "inactive"
            if action["kind"] in {"start", "reload", "restart"}:
                return "active"
        return self.initial_final_state(unit)

    def initial_final_state(self, unit):
        row = self.runtime.get(unit)
        if row is None:
            return "inactive"
        if row["load_state"] in {"masked", "not-found"}:
            return row["load_state"]
        return row.get("active_state") or "inactive"

    def initial_active(self, unit):
        row = self.runtime.get(unit)
        return row is not None and row["load_state"] == "loaded" and row["active_state"] == "active"

    def startable(self, unit):
        definition = self.defs.get(unit)
        if definition is None:
            return False
        if definition["directives"]["refuse_manual_start"]:
            return False
        row = self.runtime.get(unit)
        return row is None or row.get("load_state", "loaded") in {"", "loaded"}

    def is_active_after(self, unit, actions):
        action = actions.get(unit)
        if action:
            if action["kind"] == "stop":
                return False
            if action["kind"] in {"start", "reload", "restart"}:
                return True
        return self.initial_active(unit)

    def path_exists_after(self, path, actions):
        info = self.paths.get(path)
        if not info:
            return False
        if info["exists"]:
            return True
        return bool(info["mount_unit"]) and self.is_active_after(info["mount_unit"], actions)


def validate_schema(report):
    assert type(report) is dict
    assert set(report) == {"daemon_reloaded", "objective", "operations", "units", "warnings"}
    assert type(report["daemon_reloaded"]) is bool
    assert set(report["objective"]) == {
        "applied_priority",
        "applied_units",
        "final_active_units",
        "elapsed_sec",
        "stopped_active_units",
    }
    assert all(type(value) is int for value in report["objective"].values())
    assert type(report["operations"]) is list
    for idx, op in enumerate(report["operations"], start=1):
        assert set(op) == {"step", "action", "unit", "duration_sec", "reasons"}
        assert op["step"] == idx
        assert op["action"] in {"daemon-reload", "stop", "start", "reload", "restart"}
        assert type(op["unit"]) is str
        assert type(op["duration_sec"]) is int
        assert type(op["reasons"]) is list
        if op["action"] == "daemon-reload":
            assert op["unit"] == ""
            assert op["reasons"] == ["active_change"]
        else:
            assert op["reasons"] == ordered_reasons(set(op["reasons"]))
            assert len(op["reasons"]) == len(set(op["reasons"]))
    assert type(report["units"]) is list
    unit_names = [row["name"] for row in report["units"]]
    assert unit_names == sorted(unit_names)
    assert len(unit_names) == len(set(unit_names))
    for row in report["units"]:
        assert set(row) == {"name", "planned_action", "applied_change", "final_state", "reasons"}
        assert type(row["name"]) is str
        assert row["planned_action"] in {
            "stop",
            "start",
            "reload",
            "restart",
            "unchanged",
            "deferred",
        }
        assert type(row["applied_change"]) is bool
        assert row["final_state"] in {"active", "inactive", "failed", "masked", "not-found"}
        assert row["reasons"] == ordered_reasons(set(row["reasons"]))
        assert len(row["reasons"]) == len(set(row["reasons"]))
    assert type(report["warnings"]) is list
    warnings = [(row["unit"], row["path"], row["code"]) for row in report["warnings"]]
    assert warnings == sorted(warnings)
    for row in report["warnings"]:
        assert set(row) == {"code", "unit", "path"}
        assert row["code"] == "shadowed_change"
        assert type(row["unit"]) is str
        assert type(row["path"]) is str


def build_binary():
    assert SOURCE.exists(), "missing Go source at /workspace/cmd/systemd-window-plan/main.go"
    source_text = SOURCE.read_text(encoding="utf-8")
    forbidden = ["os/exec", "exec.Command", "syscall.Exec"]
    assert not any(token in source_text for token in forbidden)
    result = subprocess.run(
        ["go", "build", "-o", str(BINARY), "."],
        cwd=SOURCE_DIR,
        env={**os.environ, "GO111MODULE": "off"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert BINARY.exists()


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    build_binary()


def run_tool(tmp_path, data, name):
    input_path = tmp_path / f"{name}.json"
    output_path = tmp_path / "nested" / f"{name}.plan.json"
    input_path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("stale output must be replaced", encoding="utf-8")
    result = subprocess.run(
        [str(BINARY), str(input_path), str(output_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    validate_schema(report)
    return report


def base(unit, directives=None, source="vendor", path=None):
    return {
        "path": path or f"/usr/lib/systemd/system/{unit}",
        "unit": unit,
        "kind": "base",
        "source": source,
        "dropin": "",
        "reset": [],
        "directives": directives or {},
    }


def dropin(unit, name, directives=None, source="admin", reset=None, path=None):
    root = {"admin": "/etc", "runtime": "/run", "vendor": "/usr/lib"}[source]
    return {
        "path": path or f"{root}/systemd/system/{unit}.d/{name}",
        "unit": unit,
        "kind": "dropin",
        "source": source,
        "dropin": name,
        "reset": reset or [],
        "directives": directives or {},
    }


def rt(unit, active="active", load="loaded"):
    return {"unit": unit, "load_state": load, "active_state": active}


def pth(path, exists=True, mount=""):
    return {"path": path, "exists": exists, "mount_unit": mount}


def chg(unit, impact="restart", priority=1, path=None):
    return {
        "path": path or f"/usr/lib/systemd/system/{unit}",
        "unit": unit,
        "impact": impact,
        "priority": priority,
    }


def manifest(fragments, runtime, changes, maintenance=None, paths=None):
    return {
        "maintenance": {
            "deadline_sec": 20,
            "max_stopped_active": 2,
            "mount_start_limit": 2,
            "daemon_reload_sec": 1,
            "request_units": [],
            "protected_units": [],
            **(maintenance or {}),
        },
        "fragments": fragments,
        "runtime": runtime,
        "paths": paths or [],
        "changes": changes,
    }


def hidden_cases():
    cases = []
    cases.append(
        (
            "admin_base_shadows_vendor_change",
            manifest(
                [
                    base("alpha.service", {"reloadable": True, "reload_sec": 2}),
                    base(
                        "alpha.service",
                        {"reloadable": True, "reload_sec": 1, "wants": ["sidecar.service"]},
                        source="admin",
                        path="/etc/systemd/system/alpha.service",
                    ),
                    base("sidecar.service", {"start_sec": 2}),
                ],
                [rt("alpha.service"), rt("sidecar.service", "inactive")],
                [
                    chg("alpha.service", "restart", 9),
                    chg(
                        "alpha.service",
                        "reload",
                        4,
                        path="/etc/systemd/system/alpha.service",
                    ),
                ],
                {"deadline_sec": 5},
            ),
        )
    )
    cases.append(
        (
            "protected_reload_and_protected_escalation",
            manifest(
                [
                    base("safe.service", {"reloadable": True, "reload_sec": 1}),
                    base("kernel-agent.service", {"reloadable": False, "start_sec": 2, "stop_sec": 2}),
                ],
                [rt("safe.service"), rt("kernel-agent.service")],
                [
                    chg("safe.service", "reload", 5),
                    chg("kernel-agent.service", "reload", 50),
                ],
                {
                    "deadline_sec": 10,
                    "protected_units": ["safe.service", "kernel-agent.service"],
                },
            ),
        )
    )
    cases.append(
        (
            "mount_condition_rechecked_after_start",
            manifest(
                [
                    base(
                        "app.service",
                        {
                            "requires_mounts_for": ["/srv/app"],
                            "condition_paths": ["/srv/app"],
                            "start_sec": 3,
                            "stop_sec": 2,
                        },
                    ),
                    base("srv-app.mount", {"start_sec": 4}),
                ],
                [rt("app.service", "inactive"), rt("srv-app.mount", "inactive")],
                [chg("app.service", "restart", 8)],
                {"deadline_sec": 9, "request_units": ["app.service"], "mount_start_limit": 1},
                [pth("/srv/app", False, "srv-app.mount")],
            ),
        )
    )
    cases.append(
        (
            "mount_limit_forces_global_choice",
            manifest(
                [
                    base("a.service", {"requires_mounts_for": ["/srv/a"], "condition_paths": ["/srv/a"], "start_sec": 2, "stop_sec": 2}),
                    base("b.service", {"requires_mounts_for": ["/srv/b"], "condition_paths": ["/srv/b"], "start_sec": 2, "stop_sec": 2}),
                    base("srv-a.mount", {"start_sec": 3}),
                    base("srv-b.mount", {"start_sec": 3}),
                ],
                [rt("a.service"), rt("b.service"), rt("srv-a.mount", "inactive"), rt("srv-b.mount", "inactive")],
                [chg("a.service", "restart", 6), chg("b.service", "restart", 7)],
                {"deadline_sec": 20, "mount_start_limit": 1},
                [pth("/srv/a", False, "srv-a.mount"), pth("/srv/b", False, "srv-b.mount")],
            ),
        )
    )
    cases.append(
        (
            "conflict_priority_trap",
            manifest(
                [
                    base("front.service", {"conflicts": ["legacy.service"], "start_sec": 4, "stop_sec": 4}),
                    base("legacy.service", {"reloadable": True, "reload_sec": 1, "conflicts": ["front.service"], "stop_sec": 2}),
                    base("batch.service", {"reloadable": True, "reload_sec": 2}),
                    base("audit.service", {"reloadable": True, "reload_sec": 2}),
                ],
                [rt("front.service"), rt("legacy.service"), rt("batch.service"), rt("audit.service")],
                [
                    chg("front.service", "restart", 10),
                    chg("legacy.service", "reload", 8),
                    chg("batch.service", "reload", 6),
                    chg("audit.service", "reload", 6),
                ],
                {"deadline_sec": 8, "max_stopped_active": 1},
            ),
        )
    )
    cases.append(
        (
            "partof_restart_exceeds_budget",
            manifest(
                [
                    base("parent.service", {"start_sec": 5, "stop_sec": 5}),
                    base("child.service", {"part_of": ["parent.service"], "after": ["parent.service"], "start_sec": 4, "stop_sec": 4}),
                    base("small.service", {"reloadable": True, "reload_sec": 2}),
                ],
                [rt("parent.service"), rt("child.service"), rt("small.service")],
                [chg("parent.service", "restart", 9), chg("small.service", "reload", 7)],
                {"deadline_sec": 12},
            ),
        )
    )
    cases.append(
        (
            "propagated_reload_escalates_child",
            manifest(
                [
                    base("cfg.service", {"reloadable": True, "reload_sec": 1, "propagates_reload_to": ["agent.service"]}),
                    base("agent.service", {"reloadable": False, "start_sec": 3, "stop_sec": 2}),
                ],
                [rt("cfg.service"), rt("agent.service")],
                [chg("cfg.service", "reload", 5)],
                {"deadline_sec": 8},
            ),
        )
    )
    cases.append(
        (
            "weak_want_included_only_when_free_enough",
            manifest(
                [
                    base("web.service", {"reloadable": True, "reload_sec": 1, "wants": ["warm-cache.service"]}),
                    base("warm-cache.service", {"start_sec": 2}),
                ],
                [rt("web.service"), rt("warm-cache.service", "inactive")],
                [chg("web.service", "reload", 4)],
                {"deadline_sec": 4},
            ),
        )
    )
    cases.append(
        (
            "weak_want_skipped_when_it_would_stop_active_peer",
            manifest(
                [
                    base("api.service", {"reloadable": True, "reload_sec": 1, "wants": ["debug.service"]}),
                    base("debug.service", {"conflicts": ["monitor.service"], "start_sec": 1}),
                    base("monitor.service", {"conflicts": ["debug.service"], "stop_sec": 1}),
                ],
                [rt("api.service"), rt("debug.service", "inactive"), rt("monitor.service")],
                [chg("api.service", "reload", 4)],
                {"deadline_sec": 5, "max_stopped_active": 1},
            ),
        )
    )
    cases.append(
        (
            "ordering_cycle_makes_combined_plan_invalid",
            manifest(
                [
                    base("left.service", {"after": ["right.service"], "reloadable": True, "reload_sec": 1}),
                    base("right.service", {"after": ["left.service"], "reloadable": True, "reload_sec": 1}),
                    base("plain.service", {"reloadable": True, "reload_sec": 1}),
                ],
                [rt("left.service"), rt("right.service"), rt("plain.service")],
                [
                    chg("left.service", "reload", 5),
                    chg("right.service", "reload", 5),
                    chg("plain.service", "reload", 4),
                ],
                {"deadline_sec": 5},
            ),
        )
    )
    cases.append(
        (
            "dropin_reset_removes_conflict",
            manifest(
                [
                    base("new.service", {"conflicts": ["old.service"], "start_sec": 3, "stop_sec": 3}),
                    dropin("new.service", "10-reset.conf", {}, reset=["conflicts"]),
                    base("old.service", {"reloadable": True, "reload_sec": 1}),
                ],
                [rt("new.service"), rt("old.service")],
                [chg("new.service", "restart", 7), chg("old.service", "reload", 5)],
                {"deadline_sec": 12, "max_stopped_active": 0},
            ),
        )
    )
    cases.append(
        (
            "duplicate_changes_restart_dominates_reload",
            manifest(
                [base("combo.service", {"reloadable": True, "start_sec": 2, "stop_sec": 2, "reload_sec": 1})],
                [rt("combo.service")],
                [
                    chg("combo.service", "reload", 3),
                    chg("combo.service", "restart", 4),
                    chg("combo.service", "none", 100),
                ],
                {"deadline_sec": 5},
            ),
        )
    )
    cases.append(
        (
            "inactive_unrequested_change_and_daemon_reload",
            manifest(
                [
                    base("sleeping.service", {"start_sec": 2}),
                    base("live.service", {"reloadable": True, "reload_sec": 1}),
                ],
                [rt("sleeping.service", "inactive"), rt("live.service")],
                [
                    chg("sleeping.service", "restart", 8),
                    chg("live.service", "none", 0),
                ],
                {"deadline_sec": 4},
            ),
        )
    )
    cases.append(
        (
            "complete_plan_signature_tiebreak",
            manifest(
                [
                    base("a.service", {"reloadable": True, "reload_sec": 1}),
                    base("b.service", {"reloadable": True, "reload_sec": 1}),
                ],
                [rt("a.service"), rt("b.service")],
                [chg("a.service", "reload", 5), chg("b.service", "reload", 5)],
                {"deadline_sec": 2},
            ),
        )
    )
    return cases


def test_public_input_integrity():
    digest = hashlib.sha256(PUBLIC_INPUT.read_bytes()).hexdigest()
    assert digest == PUBLIC_SHA256


def test_public_case_exact(tmp_path):
    data = json.loads(PUBLIC_INPUT.read_text(encoding="utf-8"))
    expected = Reference(data).solve()
    actual = run_tool(tmp_path, data, "public")
    assert actual == expected


def test_public_default_output_is_replaced(compiled_binary):
    result = subprocess.run(
        [str(BINARY), str(PUBLIC_INPUT), str(PUBLIC_OUTPUT)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(PUBLIC_OUTPUT.read_text(encoding="utf-8"))
    validate_schema(report)
    assert report == Reference(json.loads(PUBLIC_INPUT.read_text(encoding="utf-8"))).solve()


@pytest.mark.parametrize(("name", "data"), hidden_cases())
def test_hidden_generated_cases(tmp_path, name, data):
    expected = Reference(data).solve()
    actual = run_tool(tmp_path, data, name)
    assert actual == expected
