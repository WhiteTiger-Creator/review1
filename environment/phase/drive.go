package phase

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"environment/k3"
	"environment/m8"
	"environment/v2"
)

type CaseRow struct {
	SliceID     string `json:"slice_id"`
	PeakPages   int    `json:"peak_pages"`
	BudgetCap   int    `json:"budget_cap"`
	PathMode    string `json:"path_mode"`
	HarnessExit int    `json:"harness_exit"`
}

type Report struct {
	Schema string    `json:"schema"`
	Cases  []CaseRow `json:"cases"`
}

type sampleLine struct {
	Pid   int `json:"pid"`
	Pages int `json:"pages"`
}

type rosterPlan struct {
	After int               `json:"after"`
	Patch map[string]string `json:"patch"`
}

func loadMembers(path string) (k3.Members, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	raw := map[string]string{}
	if err := json.Unmarshal(b, &raw); err != nil {
		return nil, err
	}
	out := k3.Members{}
	for k, v := range raw {
		pid, err := strconv.Atoi(k)
		if err != nil {
			continue
		}
		out[pid] = v
	}
	return out, nil
}

func loadSamples(path string) ([]sampleLine, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []sampleLine
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		var s sampleLine
		if err := json.Unmarshal([]byte(line), &s); err != nil {
			continue
		}
		out = append(out, s)
	}
	return out, sc.Err()
}

func loadRoster(path string) (*rosterPlan, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var p rosterPlan
	if err := json.Unmarshal(b, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

func applyPatch(mem k3.Members, patch map[string]string) {
	if mem == nil || patch == nil {
		return
	}
	for k, v := range patch {
		pid, err := strconv.Atoi(k)
		if err != nil {
			continue
		}
		mem[pid] = v
	}
}

func appendRec(path string, r m8.Rec) error {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	b, err := json.Marshal(r)
	if err != nil {
		return err
	}
	_, err = f.Write(append(b, '\n'))
	return err
}

func rawSampleSum(path string) (int, error) {
	samples, err := loadSamples(path)
	if err != nil {
		return 0, err
	}
	n := 0
	for _, s := range samples {
		if s.Pages > 0 {
			n += s.Pages
		}
	}
	return n, nil
}

func runLane(lane, samplePath, jnl string, mem k3.Members, st *k3.Buf, plan *rosterPlan) (int, error) {
	samples, err := loadSamples(samplePath)
	if err != nil {
		return 0, err
	}
	st.Lane = lane
	for i, s := range samples {
		peak := stepNudge(st, k3.Tick{Pid: s.Pid, Pages: s.Pages}, mem)
		if err := appendRec(jnl, m8.Rec{Kind: m8.KindSample, Pid: s.Pid, Pages: s.Pages, Lane: lane}); err != nil {
			return peak, err
		}
		if plan != nil && i == plan.After {
			applyPatch(mem, plan.Patch)
			k3.Adopt(st, mem)
			if err := appendRec(jnl, m8.Rec{Kind: m8.KindRoster, Lane: lane, Patch: plan.Patch}); err != nil {
				return st.Peak, err
			}
		}
	}
	return st.Peak, nil
}

func exitCode(peak, cap int) int {
	if peak <= cap {
		return 0
	}
	return 1
}

// DriveMatrix builds the graded report under outPath.
func DriveMatrix(root, outPath string, wide bool) error {
	cap := 48
	if wide {
		cap = 96
	}
	memPath := filepath.Join(root, "fixtures", "members", "map_a.json")
	if wide {
		memPath = filepath.Join(root, "fixtures", "members", "map_b.json")
	}
	scratch := "/app/output/scratch"
	if err := os.MkdirAll(scratch, 0o755); err != nil {
		return err
	}
	jnl := filepath.Join(scratch, "hwm.jnl")
	_ = os.Remove(jnl)
	hintPath := filepath.Join(scratch, "hwm.ckpt")
	_ = os.Remove(hintPath)

	primary := []struct {
		id   string
		file string
	}{
		{"oak", "r1.jsonl"},
		{"pine", "r2.jsonl"},
		{"ash", "r3.jsonl"},
	}
	holdout := struct {
		id   string
		file string
	}{"elm", "r4.jsonl"}

	var cases []CaseRow
	g := &v2.Gate{}
	hintPeaks := map[string]int{}
	gen := 0

	for _, ln := range primary {
		laneMem, err := loadMembers(memPath)
		if err != nil {
			return err
		}
		st := &k3.Buf{Live: map[int]int{}, Peak: 0, Lane: ln.id}
		sample := filepath.Join(root, "fixtures", "samples", ln.file)
		plan, err := loadRoster(filepath.Join(root, "fixtures", "roster", ln.id+".json"))
		if err != nil {
			return err
		}
		peak, err := runLane(ln.id, sample, jnl, laneMem, st, plan)
		if err != nil {
			return err
		}
		raw, err := rawSampleSum(sample)
		if err != nil {
			return err
		}
		hintPeaks[ln.id] = raw
		cases = append(cases, CaseRow{
			SliceID: ln.id, PeakPages: peak, BudgetCap: cap,
			PathMode: "clean", HarnessExit: exitCode(peak, cap),
		})
		gen++
		if err := appendRec(jnl, m8.Rec{Kind: m8.KindFence, Lane: ln.id, Gen: gen}); err != nil {
			return err
		}
	}
	{
		laneMem, err := loadMembers(memPath)
		if err != nil {
			return err
		}
		st := &k3.Buf{Live: map[int]int{}, Peak: 0, Lane: holdout.id}
		sample := filepath.Join(root, "fixtures", "samples", holdout.file)
		plan, err := loadRoster(filepath.Join(root, "fixtures", "roster", holdout.id+".json"))
		if err != nil {
			return err
		}
		peak, err := runLane(holdout.id, sample, jnl, laneMem, st, plan)
		if err != nil {
			return err
		}
		raw, err := rawSampleSum(sample)
		if err != nil {
			return err
		}
		hintPeaks[holdout.id] = raw
		cases = append(cases, CaseRow{
			SliceID: holdout.id, PeakPages: peak, BudgetCap: cap,
			PathMode: "clean", HarnessExit: exitCode(peak, cap),
		})
		gen++
		if err := appendRec(jnl, m8.Rec{Kind: m8.KindFence, Lane: holdout.id, Gen: gen}); err != nil {
			return err
		}
	}

	hintBody, err := json.Marshal(map[string]any{"gen": 0, "peaks": hintPeaks})
	if err != nil {
		return err
	}
	if err := os.WriteFile(hintPath, append(hintBody, '\n'), 0o644); err != nil {
		return err
	}

	memWeave, err := loadMembers(memPath)
	if err != nil {
		return err
	}
	wr, err := stepWeave(jnl, memWeave)
	if err != nil {
		return err
	}
	sealed, err := stepSeal(wr.Peaks, hintPath, wr.Gen)
	if err != nil {
		return err
	}
	mendedLanes := []struct {
		id   string
		file string
	}{}
	mendedLanes = append(mendedLanes, primary...)
	mendedLanes = append(mendedLanes, holdout)
	for _, ln := range mendedLanes {
		peak := sealed[ln.id]
		cases = append(cases, CaseRow{
			SliceID: ln.id, PeakPages: peak, BudgetCap: cap,
			PathMode: "mended", HarnessExit: exitCode(peak, cap),
		})
	}

	memReload, err := loadMembers(memPath)
	if err != nil {
		return err
	}
	st := &k3.Buf{Live: map[int]int{}, Peak: 0}
	reloadJ := filepath.Join(scratch, "hwm_reload.jnl")
	_ = os.Remove(reloadJ)
	reloadGen := 0
	for i, ln := range primary {
		if i > 0 {
			reloadGen++
			if err := appendRec(reloadJ, m8.Rec{Kind: m8.KindFence, Lane: ln.id, Gen: reloadGen}); err != nil {
				return err
			}
			if err := stepClamp(st, ln.id, g); err != nil {
				return err
			}
		}
		sample := filepath.Join(root, "fixtures", "samples", ln.file)
		plan, err := loadRoster(filepath.Join(root, "fixtures", "roster", ln.id+".json"))
		if err != nil {
			return err
		}
		peak, err := runLane(ln.id, sample, reloadJ, memReload, st, plan)
		if err != nil {
			return err
		}
		cases = append(cases, CaseRow{
			SliceID: ln.id, PeakPages: peak, BudgetCap: cap,
			PathMode: "reloaded", HarnessExit: exitCode(peak, cap),
		})
	}

	rep := Report{Schema: "peak_v1", Cases: cases}
	b, err := json.MarshalIndent(rep, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	return os.WriteFile(outPath, append(b, '\n'), 0o644)
}

// EmitHaze writes the shallow interim status file under fixtures/q9.
func EmitHaze(root string) error {
	path := filepath.Join(root, "fixtures", "q9", "haze.json")
	body := []byte(`{"schema":"haze_v0","note":"interim only","peak_pages":12}` + "\n")
	return os.WriteFile(path, body, 0o644)
}

func Must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
