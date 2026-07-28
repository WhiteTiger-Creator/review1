"""Independent reference dispatcher for ochre-panel-lamp-dispatch tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class UnsafeBoard(Exception):
    pass


def _read_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = []
    for raw in text.splitlines():
        if raw.startswith("#") or raw.strip() == "":
            continue
        lines.append(raw)
    return lines


def read_tsv(path: Path) -> list[dict[str, str]]:
    lines = _read_lines(path)
    if not lines:
        raise UnsafeBoard(f"empty {path}")
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        cols = line.split("\t")
        rows.append({header[i]: (cols[i] if i < len(cols) else "") for i in range(len(header))})
    return rows


def load_clock(panel: Path) -> tuple[int, str]:
    lines = _read_lines(panel / "clock.txt")
    if len(lines) != 1:
        raise UnsafeBoard("clock")
    parts = lines[0].split()
    if len(parts) != 2 or not parts[0].isdigit():
        raise UnsafeBoard("clock")
    return int(parts[0]), parts[1]


@dataclass
class Collapsed:
    flap_ids: list[str]
    lamp_id: str
    first_minute: int
    last_minute: int
    primary_last_minute: int
    severity: str
    raw_text: str
    clock_id: str
    primary_id: str


def collapse_flaps(flaps: list[dict[str, str]]) -> list[Collapsed]:
    by_key: dict[tuple[str, str], Collapsed] = {}
    for f in flaps:
        key = (f["lamp_id"], f["raw_text"])
        first = int(f["first_minute"])
        last = int(f["last_minute"])
        if key not in by_key:
            by_key[key] = Collapsed(
                flap_ids=[f["flap_id"]],
                lamp_id=f["lamp_id"],
                first_minute=first,
                last_minute=last,
                primary_last_minute=last,
                severity=f["severity"],
                raw_text=f["raw_text"],
                clock_id=f["clock_id"],
                primary_id=f["flap_id"],
            )
            continue
        c = by_key[key]
        c.flap_ids.append(f["flap_id"])
        if first < c.first_minute or (first == c.first_minute and f["flap_id"] < c.primary_id):
            c.first_minute = first
            c.primary_last_minute = last
            c.severity = f["severity"]
            c.primary_id = f["flap_id"]
            c.clock_id = f["clock_id"]
        c.last_minute = max(c.last_minute, last)
    return list(by_key.values())


@dataclass
class Zone:
    zone_id: str
    parent_id: str
    rack_lo: int
    rack_hi: int
    masked: int


def build_zones(rows: list[dict[str, str]]) -> dict[str, Zone]:
    zones: dict[str, Zone] = {}
    for r in rows:
        zid = r["zone_id"]
        if zid in zones:
            raise UnsafeBoard("dup zone")
        if r["masked"] not in ("0", "1"):
            raise UnsafeBoard("bad mask")
        zones[zid] = Zone(
            zone_id=zid,
            parent_id=r["parent_id"],
            rack_lo=int(r["rack_lo"]),
            rack_hi=int(r["rack_hi"]),
            masked=int(r["masked"]),
        )
    for z in zones.values():
        if z.parent_id != "-" and z.parent_id not in zones:
            raise UnsafeBoard("missing parent")
    for zid in list(zones):
        seen: set[str] = set()
        cur = zid
        while True:
            if cur in seen:
                raise UnsafeBoard("cycle")
            seen.add(cur)
            p = zones[cur].parent_id
            if p == "-":
                break
            if p not in zones:
                raise UnsafeBoard("missing parent")
            cur = p
    ids = sorted(zones)
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1 :]:
            a, b = zones[a_id], zones[b_id]
            if not (a.rack_hi < b.rack_lo or b.rack_hi < a.rack_lo):
                raise UnsafeBoard("overlap")
    return zones


def zone_for_pos(zones: dict[str, Zone], pos: int) -> Zone:
    hits = [z for z in zones.values() if z.rack_lo <= pos <= z.rack_hi]
    if len(hits) != 1:
        raise UnsafeBoard("zone resolve")
    return hits[0]


def inherited_masked(zones: dict[str, Zone], zone: Zone) -> bool:
    cur = zone
    seen: set[str] = set()
    while True:
        if cur.masked:
            return True
        if cur.parent_id == "-":
            return False
        if cur.parent_id in seen:
            raise UnsafeBoard("cycle")
        seen.add(cur.parent_id)
        if cur.parent_id not in zones:
            raise UnsafeBoard("missing parent")
        cur = zones[cur.parent_id]


def zone_depth(zones: dict[str, Zone], zone: Zone) -> int:
    depth = 0
    cur = zone
    seen: set[str] = set()
    while True:
        if cur.parent_id == "-":
            return depth
        if cur.parent_id in seen:
            raise UnsafeBoard("cycle")
        seen.add(cur.parent_id)
        if cur.parent_id not in zones:
            raise UnsafeBoard("missing parent")
        depth += 1
        cur = zones[cur.parent_id]


def masked_depth(zones: dict[str, Zone], zone: Zone) -> int:
    depth = 0
    cur = zone
    seen: set[str] = set()
    while True:
        if cur.masked:
            depth += 1
        if cur.parent_id == "-":
            return depth
        if cur.parent_id in seen:
            raise UnsafeBoard("cycle")
        seen.add(cur.parent_id)
        if cur.parent_id not in zones:
            raise UnsafeBoard("missing parent")
        cur = zones[cur.parent_id]


def shortest_route(
    corridors: list[dict[str, str]],
    location: str,
    *,
    minute: int = 0,
    hop_penalty: int = 0,
    hop_waiver: int = 0,
    hold_tax: int = 0,
    depth_tax: int = 0,
) -> dict[str, object]:
    by_runner: dict[str, list[tuple[str, str, int]]] = {}
    for c in corridors:
        mins = int(c["travel_minutes"])
        if mins < 0:
            raise UnsafeBoard("negative travel")
        by_runner.setdefault(c["runner_id"], []).append((c["from_node"], c["to_node"], mins))

    candidates: list[dict[str, object]] = []
    for runner, edges in by_runner.items():
        best: dict[tuple[str, str], int] = {}
        for frm, to, w in edges:
            key = (frm, to)
            if key not in best or w < best[key]:
                best[key] = w
        graph: dict[str, list[tuple[str, int]]] = {}
        for (frm, to), w in best.items():
            graph.setdefault(frm, []).append((to, w))
        dist = {"NOC": 0}
        path = {"NOC": "NOC"}
        changed = True
        while changed:
            changed = False
            for u in list(dist.keys()):
                for v, w in graph.get(u, []):
                    nd = dist[u] + w
                    np = path[u] + ">" + v
                    nh = np.count(">")
                    oh = path[v].count(">") if v in path else 10_000
                    if v not in dist or nd < dist[v] or (
                        nd == dist[v] and (nh < oh or (nh == oh and np < path[v]))
                    ):
                        dist[v] = nd
                        path[v] = np
                        changed = True
        if location not in dist:
            continue
        path_s = path[location]
        hops = path_s.count(">")
        billed = max(0, hops - hop_waiver)
        handoff = minute + dist[location] + billed * hop_penalty + hold_tax + depth_tax
        candidates.append(
            {
                "runner_id": runner,
                "travel": dist[location],
                "path": path_s,
                "hops": hops,
                "handoff": handoff,
            }
        )
    if not candidates:
        raise UnsafeBoard("dead end")
    candidates.sort(key=lambda r: (r["handoff"], r["runner_id"], r["path"]))
    return candidates[0]


def pick_bell(rows: list[dict[str, str]]) -> tuple[str, str | None]:
    if not rows:
        raise UnsafeBoard("no bell")
    best = min(int(r["priority"]) for r in rows)
    tied = [r for r in rows if int(r["priority"]) == best]
    if len(tied) > 1:
        rules = {r["tie_rule"] for r in tied}
        rule = tied[0]["tie_rule"]
        if len(rules) != 1 or rule in ("", "-"):
            raise UnsafeBoard("bell tie")
        tied.sort(key=lambda r: r["bell_name"])
        return tied[0]["bell_name"], rule
    return tied[0]["bell_name"], None


def choose_bell(bells: list[dict[str, str]], severity: str, color: str, in_grace: bool) -> tuple[str, str | None]:
    if in_grace:
        rows = [b for b in bells if b["color"] == color]
    else:
        rows = [b for b in bells if b["severity"] == severity and b["color"] == color]
    return pick_bell(rows)


def width_map(rows: list[dict[str, str]]) -> tuple[dict[str, int], int, int, int, int]:
    w: dict[str, int] = {}
    hop: int | None = None
    waiver: int | None = None
    hold: int | None = None
    depth: int | None = None
    for r in rows:
        n = int(r["width"])
        if r["field"] == "hop_penalty":
            if n < 0:
                raise UnsafeBoard("bad hop")
            hop = n
            continue
        if r["field"] == "hop_waiver":
            if n < 0:
                raise UnsafeBoard("bad waiver")
            waiver = n
            continue
        if r["field"] == "hold_surcharge":
            if n < 0:
                raise UnsafeBoard("bad hold")
            hold = n
            continue
        if r["field"] == "depth_penalty":
            if n < 0:
                raise UnsafeBoard("bad depth")
            depth = n
            continue
        if n <= 0:
            raise UnsafeBoard("bad width")
        w[r["field"]] = n
    if hop is None:
        raise UnsafeBoard("missing hop")
    if waiver is None:
        raise UnsafeBoard("missing waiver")
    if hold is None:
        raise UnsafeBoard("missing hold")
    if depth is None:
        raise UnsafeBoard("missing depth")
    need = [
        "beacon_lamp",
        "beacon_color",
        "beacon_zone",
        "beacon_age",
        "beacon_bell",
        "beacon_blackout",
        "beacon_message",
        "runner_id",
        "runner_lamp",
        "runner_path",
        "runner_travel",
        "runner_handoff",
        "runner_note",
    ]
    for k in need:
        if k not in w:
            raise UnsafeBoard(f"missing width {k}")
    return w, hop, waiver, hold, depth


_LOUD = {"HIGH": 3, "MED": 2, "LOW": 1}


def promote_severity(
    promotions: list[dict[str, str]], severity: str, age: int, in_grace: bool
) -> str:
    if in_grace:
        return severity
    cands = []
    for p in promotions:
        th = int(p["age_threshold"])
        if th < 0:
            raise UnsafeBoard("bad promo")
        frm, to = p["severity_from"], p["severity_to"]
        if frm not in _LOUD or to not in _LOUD:
            raise UnsafeBoard("bad promo sev")
        if frm == severity and age > th:
            cands.append(p)
    if not cands:
        return severity
    cands.sort(key=lambda p: (-int(p["age_threshold"]), _LOUD[p["severity_to"]]))
    return cands[0]["severity_to"]


def pad(text: str, width: int) -> str:
    if len(text) > width:
        raise UnsafeBoard("overflow")
    return text + (" " * (width - len(text)))


def grace_active(
    alarm: Collapsed,
    acks: list[dict[str, str]],
    minute: int,
    flap_first: dict[str, int],
) -> bool:
    ids = set(alarm.flap_ids)
    eligible = []
    for a in acks:
        if a["flap_id"] not in ids:
            continue
        ack = int(a["ack_minute"])
        if ack > minute:
            continue
        if a["flap_id"] != alarm.primary_id:
            own = flap_first.get(a["flap_id"], 0)
            if ack < own:
                continue
        eligible.append(a)
    if not eligible:
        return False
    eligible.sort(
        key=lambda a: (int(a["ack_minute"]), int(a["grace_minutes"]), a["flap_id"]),
        reverse=True,
    )
    chosen = eligible[0]
    ack = int(chosen["ack_minute"])
    grace = int(chosen["grace_minutes"])
    return grace > 0 and ack <= minute < ack + grace


def dispatch_from_dir(panel: Path) -> tuple[str, str]:
    if (panel / "FORCE_FAIL").is_file():
        raise UnsafeBoard("forced")

    minute, clock_id = load_clock(panel)
    lamps_rows = read_tsv(panel / "lamps.tsv")
    flaps = read_tsv(panel / "flaps.tsv")
    acks = read_tsv(panel / "acknowledgements.tsv")
    blackouts = read_tsv(panel / "blackouts.tsv")
    corridors = read_tsv(panel / "corridors.tsv")
    bells = read_tsv(panel / "bells.tsv")
    promotions = read_tsv(panel / "promotions.tsv")
    operators = read_tsv(panel / "operators.tsv")
    widths_rows = read_tsv(panel / "widths.tsv")

    lamps: dict[str, dict[str, str]] = {}
    for lamp_row in lamps_rows:
        if lamp_row["lamp_id"] in lamps:
            raise UnsafeBoard("dup lamp")
        lamps[lamp_row["lamp_id"]] = lamp_row

    for f in flaps:
        if f["clock_id"] != clock_id:
            raise UnsafeBoard("clock")
        if f["lamp_id"] not in lamps:
            raise UnsafeBoard("unknown lamp")
        if int(f["first_minute"]) > int(f["last_minute"]):
            raise UnsafeBoard("bad window")
    flap_ids = {f["flap_id"] for f in flaps}
    ops: set[str] = set()
    for o in operators:
        oid = o["operator_id"]
        if oid in ops:
            raise UnsafeBoard("dup op")
        ops.add(oid)
    for a in acks:
        if a["clock_id"] != clock_id:
            raise UnsafeBoard("clock")
        if a["flap_id"] not in flap_ids:
            raise UnsafeBoard("unknown ack")
        if a["operator_id"] not in ops:
            raise UnsafeBoard("unknown op")

    zones = build_zones(blackouts)
    widths, hop_penalty, hop_waiver, hold_surcharge, depth_penalty = width_map(widths_rows)
    collapsed = collapse_flaps(flaps)

    for c in collapsed:
        for a in acks:
            if a["flap_id"] in c.flap_ids and int(a["ack_minute"]) < c.first_minute:
                raise UnsafeBoard("early ack")

    active = [c for c in collapsed if c.first_minute <= minute < c.last_minute]
    flap_first = {f["flap_id"]: int(f["first_minute"]) for f in flaps}

    beacons = []
    for alarm in active:
        lamp = lamps[alarm.lamp_id]
        zone = zone_for_pos(zones, int(lamp["rack_pos"]))
        masked = inherited_masked(zones, zone)
        local_mask = bool(zone.masked)
        mdepth = masked_depth(zones, zone)
        age = minute - alarm.first_minute
        span_age = alarm.primary_last_minute - alarm.first_minute
        in_grace = grace_active(alarm, acks, minute, flap_first)
        sev = promote_severity(promotions, alarm.severity, span_age, in_grace)
        bell, tie = choose_bell(bells, sev, lamp["color"], in_grace)
        msg = alarm.raw_text
        if local_mask:
            msg = "*" + msg
        if tie is not None:
            msg += f"[tie:{tie}]"
        beacons.append(
            {
                "lamp_id": alarm.lamp_id,
                "color": lamp["color"],
                "zone_id": zone.zone_id,
                "age": str(age),
                "bell": bell,
                "blackout": "MASKED" if masked else "CLEAR",
                "message": msg,
                "silence_group": lamp["silence_group"],
                "location": lamp["location"],
                "local_mask": local_mask,
                "masked_depth": mdepth,
                "in_grace": in_grace,
            }
        )

    for b in beacons:
        if len(b["message"]) > widths["beacon_message"]:
            raise UnsafeBoard("overflow")

    group_has_mask = {b["silence_group"] for b in beacons if b["blackout"] == "MASKED"}
    group_has_local = {
        b["silence_group"] for b in beacons if b["blackout"] == "MASKED" and b["local_mask"]
    }
    best_masked: dict[str, dict] = {}
    keep: dict[str, dict] = {}
    for b in beacons:
        g = b["silence_group"]
        if g not in group_has_mask:
            keep[b["lamp_id"]] = b
            continue
        if b["blackout"] == "CLEAR":
            if g not in group_has_local:
                keep[b["lamp_id"]] = b
            continue
        if b["blackout"] != "MASKED":
            continue
        if g in group_has_local and not b["local_mask"]:
            continue
        cur = best_masked.get(g)
        if (
            cur is None
            or int(b["age"]) > int(cur["age"])
            or (int(b["age"]) == int(cur["age"]) and b["lamp_id"] < cur["lamp_id"])
        ):
            best_masked[g] = b
    for b in beacons:
        g = b["silence_group"]
        if b["blackout"] == "MASKED" and best_masked.get(g) is b:
            keep[b["lamp_id"]] = b
    beacons = sorted(
        keep.values(),
        key=lambda b: (-int(b["age"]), 0 if b["blackout"] == "MASKED" else 1, b["lamp_id"]),
    )

    runners = []
    for b in beacons:
        hold_tax = hold_surcharge if b["blackout"] == "MASKED" and not b["in_grace"] else 0
        depth_tax = int(b["masked_depth"]) * depth_penalty if b["local_mask"] else 0
        route = shortest_route(
            corridors,
            b["location"],
            minute=minute,
            hop_penalty=hop_penalty,
            hop_waiver=hop_waiver,
            hold_tax=hold_tax,
            depth_tax=depth_tax,
        )
        note = "MASK-HOLD" if b["local_mask"] else "DELIVER"
        runners.append(
            {
                "runner_id": route["runner_id"],
                "lamp_id": b["lamp_id"],
                "path": route["path"],
                "travel": str(route["travel"]),
                "handoff": str(route["handoff"]),
                "note": note,
            }
        )
    runners.sort(key=lambda r: (int(r["handoff"]), r["runner_id"], r["path"], r["lamp_id"]))

    def beacon_header() -> str:
        return "".join(
            [
                pad("LAMP", widths["beacon_lamp"]),
                pad("COLOR", widths["beacon_color"]),
                pad("ZONE", widths["beacon_zone"]),
                pad("AGE", widths["beacon_age"]),
                pad("BELL", widths["beacon_bell"]),
                pad("BLACKOUT", widths["beacon_blackout"]),
                pad("MESSAGE", widths["beacon_message"]),
            ]
        )

    def beacon_row(b: dict) -> str:
        return "".join(
            [
                pad(b["lamp_id"], widths["beacon_lamp"]),
                pad(b["color"], widths["beacon_color"]),
                pad(b["zone_id"], widths["beacon_zone"]),
                pad(b["age"], widths["beacon_age"]),
                pad(b["bell"], widths["beacon_bell"]),
                pad(b["blackout"], widths["beacon_blackout"]),
                pad(b["message"], widths["beacon_message"]),
            ]
        )

    def runner_header() -> str:
        return "".join(
            [
                pad("RUNNER", widths["runner_id"]),
                pad("LAMP", widths["runner_lamp"]),
                pad("PATH", widths["runner_path"]),
                pad("TRAVEL", widths["runner_travel"]),
                pad("HANDOFF", widths["runner_handoff"]),
                pad("NOTE", widths["runner_note"]),
            ]
        )

    def runner_row(r: dict) -> str:
        return "".join(
            [
                pad(r["runner_id"], widths["runner_id"]),
                pad(r["lamp_id"], widths["runner_lamp"]),
                pad(r["path"], widths["runner_path"]),
                pad(r["travel"], widths["runner_travel"]),
                pad(r["handoff"], widths["runner_handoff"]),
                pad(r["note"], widths["runner_note"]),
            ]
        )

    blines = [beacon_header()] + [beacon_row(b) for b in beacons]
    rlines = [runner_header()] + [runner_row(r) for r in runners]
    return "\n".join(blines) + "\n", "\n".join(rlines) + "\n"


def parse_fixed(text: str, widths: list[int]) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        cols = []
        pos = 0
        for w in widths:
            cols.append(line[pos : pos + w].rstrip(" "))
            pos += w
        rows.append(cols)
    return rows
