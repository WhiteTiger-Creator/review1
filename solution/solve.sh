#!/bin/bash
set -euo pipefail

# Oracle for graduate-the-erased-cohort.
#
# Derivation, from the surviving records only:
# 1. From the /srv/switchboard calendars, per-shift per-pod presence;
#    expected delivery per shift/class is present-hosts x 480 host-minutes
#    (the exporter NOTES define delivery as scheduler-confirmed per-minute
#    accounting, so off-fault cells match expectation exactly).
# 2. Diffing expected vs /srv/metrics/exporter/loadfeed.tsv isolates two
#    anomalies: an all-class dip in S45 whose per-host size matches the
#    yard bounce the incident note records (4:23-4:40 into S45), and
#    carousel-only shortfalls S38..S45 whose full-shift magnitudes equal
#    exactly one pod's present-count x 480 on every interior shift.
# 3. The carousel feeder sheet says degradation faults latch until a power
#    cycle; the only power cycle in the window is the S45 bounce. One
#    latched feeder therefore ran degraded over one contiguous span ending
#    at the bounce; the edge-shift shortfalls place its start inside S38.
# 4. The intake standard counts full wall-clock hours of all-class pod
#    concurrency only; hours overlapping the degradation (for the affected
#    pod) or the bounce (for every pod) do not qualify. Per-host credit
#    follows from calendar presence; dispositions, continuation slots and
#    restarts follow from the standard's rules as written.

python3 - <<'PY' > /tmp/oracle_dispositions.sh
import os, re
from collections import defaultdict

SRV = "/srv"
SHIFTS, SHIFT_MIN, REQ, CAP_SHIFTS, PODCAP = 48, 480, 120, 54, 8
CLASSES = ["hammer", "carousel", "flood"]

pods, racked = {}, {}
with open(f"{SRV}/switchboard/roster.tsv") as f:
    next(f)
    for ln in f:
        h, pod, rack, rk = ln.split()
        pods[h], racked[h] = pod, int(rk[1:])

load, fut_reim = defaultdict(set), defaultdict(set)
cal_dir = f"{SRV}/switchboard/calendars"
for fn in os.listdir(cal_dir):
    h = fn[:-4]
    for ln in open(f"{cal_dir}/{fn}"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        rng, kind = ln.split("\t")
        m = re.match(r"S(\d+)(?:\.\.S(\d+))?$", rng)
        a = int(m.group(1)); b = int(m.group(2) or a)
        for s in range(a, b + 1):
            if kind == "load":
                load[h].add(s)
            elif kind == "reimage" and s > SHIFTS:
                fut_reim[h].add(s)

hosts = sorted(pods)
def present(pod, s):
    return sum(1 for h in hosts if pods[h] == pod and s in load[h])

actual = {}
with open(f"{SRV}/metrics/exporter/loadfeed.tsv") as f:
    next(f)
    for ln in f:
        sid, cls, mins = ln.split()
        actual[(int(sid[1:]), cls)] = int(mins)

short = {}
for s in range(1, SHIFTS + 1):
    tot = sum(present(p, s) for p in ("north", "mid", "south"))
    for cls in CLASSES:
        short[(s, cls)] = tot * SHIFT_MIN - actual[(s, cls)]

# the all-class dip is the recorded yard bounce (incident note: 4:23-4:40)
dip = [s for s in range(1, SHIFTS + 1)
       if all(short[(s, c)] > 0 for c in CLASSES)]
assert dip == [45]
BOUNCE = (45, 263, 280)
tot45 = sum(present(p, 45) for p in ("north", "mid", "south"))
assert short[(45, "hammer")] == tot45 * (BOUNCE[2] - BOUNCE[1])

# carousel-only shortfalls: attribute the latched feeder's pod
blip = tot45 * (BOUNCE[2] - BOUNCE[1])
deg_shifts = sorted(s for s in range(1, SHIFTS + 1)
                    if short[(s, "carousel")] - (blip if s == 45 else 0) > 0)
interior = deg_shifts[1:-1]
for s in interior:
    fit = [p for p in ("north", "mid", "south")
           if short[(s, "carousel")] == present(p, s) * SHIFT_MIN]
    assert fit == ["mid"], (s, fit)
DEGP = "mid"
s0, sN = deg_shifts[0], deg_shifts[-1]
lost0 = short[(s0, "carousel")] // present(DEGP, s0)
DEG_START = (s0, SHIFT_MIN - lost0)
lostN = (short[(sN, "carousel")] - blip) // present(DEGP, sN)
assert sN == BOUNCE[0] and lostN == BOUNCE[1]   # the latch ends at the bounce

def qhours(pod, s):
    q = 0
    for h in range(8):
        lo, hi = h * 60, (h + 1) * 60
        bad = False
        if s == BOUNCE[0] and not (hi <= BOUNCE[1] or lo >= BOUNCE[2]):
            bad = True
        if pod == DEGP and DEG_START[0] <= s <= BOUNCE[0]:
            dlo = DEG_START[1] if s == DEG_START[0] else 0
            dhi = BOUNCE[1] if s == BOUNCE[0] else SHIFT_MIN
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
keep = [h for h in rest if h not in restart]
sl2 = assign(keep)

print("#!/bin/bash\nset -euo pipefail")
for h in grads:
    print(f"steward dispose {h} graduate")
for h in keep:
    print(f"steward dispose {h} continue "
          + ",".join(f"S{s}" for s in sl2[h]))
for h in restart:
    print(f"steward dispose {h} restart")
print("steward resume")
PY

# wait for the daemon socket (the CLI self-starts stewd; poll, never a fixed sleep)
for _ in $(seq 1 60); do
    if steward status >/dev/null 2>&1; then break; fi
    sleep 0.25
done
steward status
bash /tmp/oracle_dispositions.sh
steward status
