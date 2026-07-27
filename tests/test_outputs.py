"""Verifier for graduate-the-erased-cohort.

Recomputes the whole ground truth independently from the pristine record
copies bundled next to this file (never from agent-writable state), then
checks the applied steward state against it. Grading is by outcome: any
route that produced the correct applied state passes.
"""

import os
import re
import socket
import subprocess
import time
from collections import defaultdict
from pathlib import Path

PRISTINE = Path(__file__).resolve().parent / "pristine" / "srv"
SRV_LIVE = Path(os.environ.get("GRAD_SRV", "/srv"))
STATE = Path(os.environ.get("GRAD_STATE", "/opt/steward/state"))
SOCK = os.environ.get("GRAD_SOCK", "/run/steward.sock")

SHIFTS, SHIFT_MIN, REQ, CAP_SHIFTS, PODCAP = 48, 480, 120, 54, 8
CLASSES = ("hammer", "carousel", "flood")
PODS = ("north", "mid", "south")


# ---------------------------------------------------------------- recompute

def _world():
    pods, racked = {}, {}
    with open(PRISTINE / "switchboard" / "roster.tsv") as f:
        next(f)
        for ln in f:
            h, pod, _rack, rk = ln.split()
            pods[h] = pod
            racked[h] = int(rk[1:])
    load = defaultdict(set)
    fut_reim = defaultdict(set)
    for fn in sorted((PRISTINE / "switchboard" / "calendars").iterdir()):
        h = fn.name[:-4]
        for ln in fn.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            rng, kind = ln.split("\t")
            m = re.match(r"S(\d+)(?:\.\.S(\d+))?$", rng)
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            for s in range(a, b + 1):
                if kind == "load":
                    load[h].add(s)
                elif kind == "reimage" and s > SHIFTS:
                    fut_reim[h].add(s)
    return pods, racked, load, fut_reim


def _truth():
    pods, racked, load, fut_reim = _world()
    hosts = sorted(pods)

    def present(pod, s):
        return sum(1 for h in hosts if pods[h] == pod and s in load[h])

    actual = {}
    with open(PRISTINE / "metrics" / "exporter" / "loadfeed.tsv") as f:
        next(f)
        for ln in f:
            sid, cls, mins = ln.split()
            actual[(int(sid[1:]), cls)] = int(mins)

    short = {}
    for s in range(1, SHIFTS + 1):
        tot = sum(present(p, s) for p in PODS)
        for cls in CLASSES:
            short[(s, cls)] = tot * SHIFT_MIN - actual[(s, cls)]

    # the all-class dip is the recorded yard bounce (incident note timing:
    # stopped 4:23 into the shift, resumed 4:40 -> minutes 263..280)
    dip = [s for s in range(1, SHIFTS + 1)
           if all(short[(s, c)] > 0 for c in CLASSES)]
    assert len(dip) == 1, f"bounce dip shifts {dip}"
    bounce = (dip[0], 263, 280)
    tot_b = sum(present(p, bounce[0]) for p in PODS)
    assert short[(bounce[0], "hammer")] == tot_b * (bounce[2] - bounce[1])
    blip = tot_b * (bounce[2] - bounce[1])

    deg = sorted(s for s in range(1, SHIFTS + 1)
                 if short[(s, "carousel")] - (blip if s == bounce[0] else 0) > 0)
    for s in deg[1:-1]:
        fit = [p for p in PODS
               if short[(s, "carousel")] == present(p, s) * SHIFT_MIN]
        assert fit == ["mid"], f"S{s} pod fit {fit}"
    degp = "mid"
    s0, sN = deg[0], deg[-1]
    lost0 = short[(s0, "carousel")] // present(degp, s0)
    deg_start = (s0, SHIFT_MIN - lost0)
    lostN = (short[(sN, "carousel")] - blip) // present(degp, sN)
    assert sN == bounce[0] and lostN == bounce[1]

    def qhours(pod, s):
        q = 0
        for hh in range(8):
            lo, hi = hh * 60, (hh + 1) * 60
            bad = False
            if s == bounce[0] and not (hi <= bounce[1] or lo >= bounce[2]):
                bad = True
            if pod == degp and deg_start[0] <= s <= bounce[0]:
                dlo = deg_start[1] if s == deg_start[0] else 0
                dhi = bounce[1] if s == bounce[0] else SHIFT_MIN
                if not (hi <= dlo or lo >= dhi):
                    bad = True
            if not bad:
                q += 1
        return q

    credit = {h: sum(qhours(pods[h], s)
                     for s in range(1, SHIFTS + 1) if s in load[h])
              for h in hosts}
    grads = sorted(h for h in hosts if credit[h] >= REQ)

    def assign(cands):
        need = {h: REQ - credit[h] for h in cands}
        slots = defaultdict(list)
        s = SHIFTS + 1
        while any(need[h] > 0 for h in cands) and s <= SHIFTS + 80:
            used = defaultdict(int)
            for h in sorted((x for x in cands if need[x] > 0),
                            key=lambda x: (-need[x], x)):
                if s in fut_reim[h] or used[pods[h]] >= PODCAP:
                    continue
                slots[h].append(s)
                used[pods[h]] += 1
                need[h] = max(0, need[h] - 8)
            s += 1
        return slots

    rest = [h for h in hosts if credit[h] < REQ]
    sl1 = assign(rest)
    restart = sorted(h for h in rest
                     if not sl1[h] or sl1[h][-1] > racked[h] + CAP_SHIFTS - 1)
    keep = sorted(h for h in rest if h not in restart)
    slots = assign(keep)

    # pool placement: per pod, graduates in rack order, positions 1..k
    rack = {}
    with open(PRISTINE / "switchboard" / "roster.tsv") as f:
        next(f)
        for ln in f:
            h, _pod, rk, _r = ln.split()
            rack[h] = rk
    pools = {}
    for pod in PODS:
        sel = sorted((h for h in grads if pods[h] == pod), key=lambda h: rack[h])
        for i, h in enumerate(sel, 1):
            pools[h] = (f"{pod}-cell", i)
    return {
        "hosts": hosts, "credit": credit, "grads": grads,
        "keep": keep, "restart": restart,
        "slots": {h: slots[h] for h in keep}, "pools": pools,
    }


def _applied():
    out = {}
    p = STATE / "applied.tsv"
    if not p.exists():
        return None
    for ln in p.read_text().splitlines():
        parts = ln.split("\t")
        if len(parts) == 2:
            out[parts[0]] = (parts[1], [])
        elif len(parts) == 3:
            sl = [int(x[1:]) for x in parts[2].split(",") if x]
            out[parts[0]] = (parts[1], sl)
    return out


# ------------------------------------------------------------------- tests

def test_records_untouched():
    """The surviving records under /srv are read-only evidence; every byte
    must match the pristine copies bundled with the verifier."""
    for f in sorted(PRISTINE.rglob("*")):
        if not f.is_file():
            continue
        live = SRV_LIVE / f.relative_to(PRISTINE)
        assert live.exists(), f"missing record {live}"
        assert live.read_bytes() == f.read_bytes(), f"modified record {live}"


def test_every_host_disposed_exactly_once():
    """The resume gate requires one applied disposition per rostered host;
    the applied ledger must cover the roster exactly."""
    t = _truth()
    ap = _applied()
    assert ap is not None, "no applied disposition state (resume never ran?)"
    assert sorted(ap) == t["hosts"], (
        f"applied ledger covers {sorted(ap)}; roster is {t['hosts']}")


def test_no_unqualified_host_graduated():
    """No host below the standard's 120 qualified hours may enter a
    production cell: graduating one serves an unburned host."""
    t = _truth()
    ap = _applied() or {}
    wrong = sorted(h for h, (v, _) in ap.items()
                   if v == "graduate" and h not in t["grads"])
    assert not wrong, (
        f"hosts graduated below the standard: {wrong} "
        f"(qualified hours: { {h: t['credit'][h] for h in wrong} })")


def test_every_qualified_host_graduated():
    """Every host meeting the standard must graduate now; withholding a
    qualified host breaches intake."""
    t = _truth()
    ap = _applied() or {}
    missing = sorted(h for h in t["grads"]
                     if ap.get(h, ("", []))[0] != "graduate")
    assert not missing, f"qualified hosts not graduated: {missing}"


def test_restart_set_exact():
    """Exactly the hosts that cannot complete within the standard's yard
    limit restart; restarting a feasible host discards banked burn-in."""
    t = _truth()
    ap = _applied() or {}
    got = sorted(h for h, (v, _) in ap.items() if v == "restart")
    assert got == t["restart"], (
        f"restart set {got}; the standard's yard limit yields {t['restart']}")


def test_continue_slots_exact():
    """Continuation slots must follow the standard's assignment rule
    (earliest future shifts, reimage skips, pod capacity 8, larger
    remainders first, host id on ties)."""
    t = _truth()
    ap = _applied() or {}
    bad = {}
    for h in t["keep"]:
        verb, sl = ap.get(h, ("", []))
        if verb != "continue" or sl != t["slots"][h]:
            bad[h] = {"applied": (verb, sl), "rule": t["slots"][h]}
    assert not bad, f"continuation slots diverge from the standard: {bad}"


def test_pool_placement():
    """Graduates enter their pod's production cell at the next free
    position in rack order; the pools ledger must match the rule."""
    t = _truth()
    p = STATE / "pools.tsv"
    assert p.exists(), "no pools ledger"
    got = {}
    for ln in p.read_text().splitlines():
        if not ln.strip():
            continue
        h, cell, pos = ln.split("\t")
        got[h] = (cell, int(pos))
    assert got == t["pools"], f"pools {got}; rule gives {t['pools']}"


def test_intake_serving():
    """The gate must be open and the steward daemon serving; the verifier
    speaks the daemon socket directly."""
    gate = (STATE / "gate").read_text().split()
    assert gate and gate[0] == "open", f"gate state {gate}"
    if not os.path.exists(SOCK):
        subprocess.Popen(["/usr/local/bin/stewd"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    reply = ""
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(SOCK)
            s.sendall(b"STATUS\n")
            reply = s.recv(4096).decode()
            s.close()
            break
        except OSError:
            time.sleep(0.25)
    assert "gate=open" in reply and "serving=yes" in reply, (
        f"steward status reply: {reply!r}")
