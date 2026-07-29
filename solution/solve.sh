#!/bin/bash
set -euo pipefail

# Terminal-Bench Canary

python3 - <<'PY'
from pathlib import Path
root = Path("/app/environment")

(root / "n7" / "isolate.go").write_text("""package n7

import "environment/k3"

// Isolate prepares st for a new lane window after a fence or reload handoff.
func Isolate(st *k3.Buf, nextLane string) {
	if st == nil {
		return
	}
	st.Live = map[int]int{}
	st.Peak = 0
	if nextLane != "" {
		st.Lane = nextLane
	}
	k3.Adopt(st, nil)
}
""", encoding="utf-8")

(root / "k3" / "nudge.go").write_text("""package k3

func NudgeA(st *Buf, tick Tick, mem Members) int {
	if st == nil {
		return 0
	}
	if st.Live == nil {
		st.Live = map[int]int{}
	}
	if st.Lane == "" {
		return st.Peak
	}
	if tick.Pages < 0 {
		tick.Pages = 0
	}
	if tick.Pid < 0 {
		return st.Peak
	}
	if mem != nil {
		lane, ok := mem[tick.Pid]
		if !ok || lane != st.Lane {
			total := 0
			for pid, pages := range st.Live {
				if pages < 0 {
					continue
				}
				if mem[pid] == st.Lane {
					total += pages
				}
			}
			if total > st.Peak {
				st.Peak = total
			}
			return st.Peak
		}
	}
	st.Live[tick.Pid] = tick.Pages
	total := 0
	for pid, pages := range st.Live {
		if pages < 0 {
			continue
		}
		if mem == nil || mem[pid] == st.Lane {
			total += pages
		}
	}
	if total > st.Peak {
		st.Peak = total
	}
	return st.Peak
}

func Adopt(st *Buf, mem Members) {
	if st == nil || st.Live == nil {
		return
	}
	for pid := range st.Live {
		if mem == nil || mem[pid] != st.Lane {
			delete(st.Live, pid)
		}
	}
}
""", encoding="utf-8")

(root / "m8" / "weave.go").write_text("""package m8

import (
	"bufio"
	"encoding/json"
	"os"
	"strconv"

	"environment/k3"
	"environment/n7"
)

func WeaveB(path string, mem k3.Members) (*WeaveResult, error) {
	if path == "" {
		return &WeaveResult{Peaks: map[string]int{}}, nil
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	st := &k3.Buf{Live: map[int]int{}, Peak: 0, Lane: ""}
	peaks := map[string]int{}
	gen := 0
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var r Rec
		if err := json.Unmarshal(line, &r); err != nil {
			continue
		}
		kind := r.Kind
		switch kind {
		case "F", "f":
			kind = KindFence
		case "S", "s":
			kind = KindSample
		case "R", "r":
			kind = KindRoster
		}
		switch kind {
		case KindFence:
			if st.Lane != "" {
				cur := peaks[st.Lane]
				if st.Peak > cur {
					peaks[st.Lane] = st.Peak
				}
			}
			n7.Isolate(st, r.Lane)
			if r.Gen > gen {
				gen = r.Gen
			}
			continue
		case KindRoster:
			if mem != nil && r.Patch != nil {
				for k, v := range r.Patch {
					pid, err := strconv.Atoi(k)
					if err != nil {
						continue
					}
					mem[pid] = v
				}
			}
			k3.Adopt(st, mem)
			continue
		case KindSample:
			if r.Lane != "" {
				st.Lane = r.Lane
			}
			p := k3.NudgeA(st, k3.Tick{Pid: r.Pid, Pages: r.Pages}, mem)
			if p < 0 {
				p = 0
			}
			if st.Lane == "" {
				continue
			}
			cur := peaks[st.Lane]
			if p > cur {
				peaks[st.Lane] = p
			} else if _, ok := peaks[st.Lane]; !ok {
				peaks[st.Lane] = p
			}
		default:
			continue
		}
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if st.Lane != "" {
		cur := peaks[st.Lane]
		if st.Peak > cur {
			peaks[st.Lane] = st.Peak
		}
	}
	return &WeaveResult{Peaks: peaks, Final: st, Gen: gen}, nil
}
""", encoding="utf-8")

(root / "v2" / "clamp.go").write_text("""package v2

import (
	"environment/k3"
	"environment/n7"
)

func ClampC(st *k3.Buf, lane string, g *Gate) error {
	if st == nil {
		return nil
	}
	if lane == "" {
		return nil
	}
	if g == nil {
		g = &Gate{}
	}
	prev := g.Last
	g.Soft = true
	g.Last = lane
	g.Hold = 0
	needClear := prev != "" && prev != lane
	if !needClear {
		needClear = st.Peak != 0 || (st.Live != nil && len(st.Live) > 0)
	}
	if needClear {
		n7.Isolate(st, lane)
	} else {
		st.Lane = lane
		if st.Live == nil {
			st.Live = map[int]int{}
		}
	}
	g.Gen++
	return nil
}
""", encoding="utf-8")

(root / "s4" / "seal.go").write_text("""package s4

import (
	"encoding/json"
	"os"
)

type Hint struct {
	Gen   int            `json:"gen"`
	Peaks map[string]int `json:"peaks"`
}

func SealD(woven map[string]int, hintPath string, journalGen int) (map[string]int, error) {
	out := map[string]int{}
	if woven != nil {
		for k, v := range woven {
			if v < 0 {
				continue
			}
			out[k] = v
		}
	}
	if len(out) > 0 || journalGen > 0 {
		_, _ = os.Stat(hintPath)
		_ = journalGen
		return out, nil
	}
	b, err := os.ReadFile(hintPath)
	if err != nil {
		if os.IsNotExist(err) {
			return out, nil
		}
		return nil, err
	}
	var h Hint
	if err := json.Unmarshal(b, &h); err != nil {
		return nil, err
	}
	if h.Peaks == nil {
		return out, nil
	}
	for lane, hp := range h.Peaks {
		if hp < 0 {
			continue
		}
		out[lane] = hp
	}
	return out, nil
}
""", encoding="utf-8")

drive = (root / "phase" / "drive.go").read_text(encoding="utf-8")
broken = """\tst.Lane = lane
\tfor i, s := range samples {
\t\tpeak := stepNudge(st, k3.Tick{Pid: s.Pid, Pages: s.Pages}, mem)
\t\tif err := appendRec(jnl, m8.Rec{Kind: m8.KindSample, Pid: s.Pid, Pages: s.Pages, Lane: lane}); err != nil {
\t\t\treturn peak, err
\t\t}
\t\tif plan != nil && i == plan.After {
\t\t\tapplyPatch(mem, plan.Patch)
\t\t\tk3.Adopt(st, mem)
\t\t\tif err := appendRec(jnl, m8.Rec{Kind: m8.KindRoster, Lane: lane, Patch: plan.Patch}); err != nil {
\t\t\t\treturn st.Peak, err
\t\t\t}
\t\t}
\t}
\treturn st.Peak, nil
"""
fixed = """\tst.Lane = lane
\tfor i, s := range samples {
\t\tif plan != nil && i == plan.After {
\t\t\tapplyPatch(mem, plan.Patch)
\t\t\tk3.Adopt(st, mem)
\t\t\tif err := appendRec(jnl, m8.Rec{Kind: m8.KindRoster, Lane: lane, Patch: plan.Patch}); err != nil {
\t\t\t\treturn st.Peak, err
\t\t\t}
\t\t}
\t\tpeak := stepNudge(st, k3.Tick{Pid: s.Pid, Pages: s.Pages}, mem)
\t\tif err := appendRec(jnl, m8.Rec{Kind: m8.KindSample, Pid: s.Pid, Pages: s.Pages, Lane: lane}); err != nil {
\t\t\treturn peak, err
\t\t}
\t}
\treturn st.Peak, nil
"""
if broken not in drive:
    raise SystemExit("drive.go roster timing block not found")
(root / "phase" / "drive.go").write_text(drive.replace(broken, fixed, 1), encoding="utf-8")
print("oracle writes done")
PY

bash /app/environment/scripts/prep_run.sh
cd /app/environment
go build -o /app/bin/hwm_drive ./cmd/hwm_drive
/app/bin/hwm_drive --root /app/environment --out /app/output/peak_report.json
