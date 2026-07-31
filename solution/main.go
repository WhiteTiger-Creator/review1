package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var reasonOrder = []string{
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
}

var reasonRank = func() map[string]int {
	out := make(map[string]int)
	for idx, reason := range reasonOrder {
		out[reason] = idx
	}
	return out
}()

type inputFile struct {
	Maintenance maintenance    `json:"maintenance"`
	Fragments   []fragment     `json:"fragments"`
	Runtime     []runtimeState `json:"runtime"`
	Paths       []pathState    `json:"paths"`
	Changes     []change       `json:"changes"`
}

type maintenance struct {
	DeadlineSec      int      `json:"deadline_sec"`
	MaxStoppedActive int      `json:"max_stopped_active"`
	MountStartLimit  int      `json:"mount_start_limit"`
	DaemonReloadSec  int      `json:"daemon_reload_sec"`
	RequestUnits     []string `json:"request_units"`
	ProtectedUnits   []string `json:"protected_units"`
}

type fragment struct {
	Path       string        `json:"path"`
	Unit       string        `json:"unit"`
	Kind       string        `json:"kind"`
	Source     string        `json:"source"`
	Dropin     string        `json:"dropin"`
	Reset      []string      `json:"reset"`
	Directives rawDirectives `json:"directives"`
}

type rawDirectives struct {
	Requires           []string `json:"requires"`
	Wants              []string `json:"wants"`
	After              []string `json:"after"`
	Before             []string `json:"before"`
	Conflicts          []string `json:"conflicts"`
	PartOf             []string `json:"part_of"`
	PropagatesReloadTo []string `json:"propagates_reload_to"`
	RequiresMountsFor  []string `json:"requires_mounts_for"`
	ConditionPaths     []string `json:"condition_paths"`
	Reloadable         *bool    `json:"reloadable"`
	RefuseManualStart  *bool    `json:"refuse_manual_start"`
	StartSec           *int     `json:"start_sec"`
	StopSec            *int     `json:"stop_sec"`
	ReloadSec          *int     `json:"reload_sec"`
}

type directives struct {
	Requires           []string
	Wants              []string
	After              []string
	Before             []string
	Conflicts          []string
	PartOf             []string
	PropagatesReloadTo []string
	RequiresMountsFor  []string
	ConditionPaths     []string
	Reloadable         bool
	RefuseManualStart  bool
	StartSec           int
	StopSec            int
	ReloadSec          int
}

type runtimeState struct {
	Unit        string `json:"unit"`
	LoadState   string `json:"load_state"`
	ActiveState string `json:"active_state"`
}

type pathState struct {
	Path      string `json:"path"`
	Exists    bool   `json:"exists"`
	MountUnit string `json:"mount_unit"`
}

type change struct {
	Path     string `json:"path"`
	Unit     string `json:"unit"`
	Impact   string `json:"impact"`
	Priority int    `json:"priority"`
}

type unitDef struct {
	Name       string
	BasePath   string
	Directives directives
}

type changeGroup struct {
	Unit       string
	Priority   int
	HasRestart bool
	HasReload  bool
}

type rootCandidate struct {
	Unit             string
	Action           string
	Priority         int
	Reasons          []string
	BlockedProtected bool
}

type actionPlan struct {
	Kind    string
	Reasons map[string]bool
}

type planState struct {
	Actions map[string]*actionPlan
}

type warningOut struct {
	Code string `json:"code"`
	Unit string `json:"unit"`
	Path string `json:"path"`
}

type operationOut struct {
	Step        int      `json:"step"`
	Action      string   `json:"action"`
	Unit        string   `json:"unit"`
	DurationSec int      `json:"duration_sec"`
	Reasons     []string `json:"reasons"`
}

type unitOut struct {
	Name          string   `json:"name"`
	PlannedAction string   `json:"planned_action"`
	AppliedChange bool     `json:"applied_change"`
	FinalState    string   `json:"final_state"`
	Reasons       []string `json:"reasons"`
}

type objectiveOut struct {
	AppliedPriority   int `json:"applied_priority"`
	AppliedUnits      int `json:"applied_units"`
	FinalActiveUnits  int `json:"final_active_units"`
	ElapsedSec        int `json:"elapsed_sec"`
	StoppedActiveUnit int `json:"stopped_active_units"`
}

type reportOut struct {
	DaemonReloaded bool           `json:"daemon_reloaded"`
	Objective      objectiveOut   `json:"objective"`
	Operations     []operationOut `json:"operations"`
	Units          []unitOut      `json:"units"`
	Warnings       []warningOut   `json:"warnings"`
}

type candidateReport struct {
	Report    reportOut
	Signature []string
}

type solver struct {
	Input            inputFile
	Defs             map[string]unitDef
	Runtime          map[string]runtimeState
	Paths            map[string]pathState
	ActivePaths      map[string]bool
	Protected        map[string]bool
	Requested        map[string]bool
	Conflicts        map[string]map[string]bool
	PartOfReverse    map[string][]string
	RootByUnit       map[string]rootCandidate
	Roots            []rootCandidate
	InactiveChanged  map[string]bool
	Warnings         []warningOut
	DaemonReloaded   bool
	MaterializedUnit map[string]bool
}

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: systemd-window-plan INPUT_JSON OUTPUT_JSON")
		os.Exit(2)
	}

	inputPath := os.Args[1]
	outputPath := os.Args[2]
	raw, err := os.ReadFile(inputPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read input: %v\n", err)
		os.Exit(1)
	}
	var parsed inputFile
	if err := json.Unmarshal(raw, &parsed); err != nil {
		fmt.Fprintf(os.Stderr, "parse input: %v\n", err)
		os.Exit(1)
	}

	s := newSolver(parsed)
	report := s.solve()

	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "create output directory: %v\n", err)
		os.Exit(1)
	}
	encoded, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "encode output: %v\n", err)
		os.Exit(1)
	}
	encoded = append(encoded, '\n')
	if err := os.WriteFile(outputPath, encoded, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write output: %v\n", err)
		os.Exit(1)
	}
}

func newSolver(in inputFile) *solver {
	defs, activePaths := materialize(in.Fragments)
	s := &solver{
		Input:            in,
		Defs:             defs,
		Runtime:          map[string]runtimeState{},
		Paths:            map[string]pathState{},
		ActivePaths:      activePaths,
		Protected:        map[string]bool{},
		Requested:        map[string]bool{},
		Conflicts:        map[string]map[string]bool{},
		PartOfReverse:    map[string][]string{},
		RootByUnit:       map[string]rootCandidate{},
		InactiveChanged:  map[string]bool{},
		MaterializedUnit: map[string]bool{},
	}
	for name := range defs {
		s.MaterializedUnit[name] = true
	}
	for _, rt := range in.Runtime {
		s.Runtime[rt.Unit] = rt
	}
	for _, path := range in.Paths {
		s.Paths[path.Path] = path
	}
	for _, unit := range in.Maintenance.ProtectedUnits {
		s.Protected[unit] = true
	}
	for _, unit := range in.Maintenance.RequestUnits {
		s.Requested[unit] = true
	}
	s.buildRelations()
	s.buildChanges()
	return s
}

func materialize(fragments []fragment) (map[string]unitDef, map[string]bool) {
	bases := map[string]fragment{}
	dropins := map[string]fragment{}
	for _, frag := range fragments {
		if frag.Kind == "base" {
			current, ok := bases[frag.Unit]
			if !ok || betterFragment(frag, current) {
				bases[frag.Unit] = frag
			}
		}
		if frag.Kind == "dropin" {
			key := frag.Unit + "\x00" + frag.Dropin
			current, ok := dropins[key]
			if !ok || betterFragment(frag, current) {
				dropins[key] = frag
			}
		}
	}

	dropinsByUnit := map[string][]fragment{}
	for _, frag := range dropins {
		dropinsByUnit[frag.Unit] = append(dropinsByUnit[frag.Unit], frag)
	}
	for unit := range dropinsByUnit {
		sort.Slice(dropinsByUnit[unit], func(i, j int) bool {
			if dropinsByUnit[unit][i].Dropin != dropinsByUnit[unit][j].Dropin {
				return dropinsByUnit[unit][i].Dropin < dropinsByUnit[unit][j].Dropin
			}
			return dropinsByUnit[unit][i].Path < dropinsByUnit[unit][j].Path
		})
	}

	activePaths := map[string]bool{}
	defs := map[string]unitDef{}
	for unit, base := range bases {
		d := defaultDirectives()
		applyRawDirectives(&d, base.Reset, base.Directives)
		activePaths[base.Path] = true
		for _, dropin := range dropinsByUnit[unit] {
			applyRawDirectives(&d, dropin.Reset, dropin.Directives)
			activePaths[dropin.Path] = true
		}
		finalizeDirectives(&d)
		defs[unit] = unitDef{Name: unit, BasePath: base.Path, Directives: d}
	}
	return defs, activePaths
}

func sourceRank(source string) int {
	switch source {
	case "admin":
		return 3
	case "runtime":
		return 2
	case "vendor":
		return 1
	default:
		return 0
	}
}

func betterFragment(left, right fragment) bool {
	if sourceRank(left.Source) != sourceRank(right.Source) {
		return sourceRank(left.Source) > sourceRank(right.Source)
	}
	return left.Path < right.Path
}

func defaultDirectives() directives {
	return directives{
		StartSec:  1,
		StopSec:   1,
		ReloadSec: 1,
	}
}

func applyRawDirectives(d *directives, reset []string, raw rawDirectives) {
	sort.Strings(reset)
	for _, name := range reset {
		switch name {
		case "requires":
			d.Requires = nil
		case "wants":
			d.Wants = nil
		case "after":
			d.After = nil
		case "before":
			d.Before = nil
		case "conflicts":
			d.Conflicts = nil
		case "part_of":
			d.PartOf = nil
		case "propagates_reload_to":
			d.PropagatesReloadTo = nil
		case "requires_mounts_for":
			d.RequiresMountsFor = nil
		case "condition_paths":
			d.ConditionPaths = nil
		}
	}
	d.Requires = append(d.Requires, raw.Requires...)
	d.Wants = append(d.Wants, raw.Wants...)
	d.After = append(d.After, raw.After...)
	d.Before = append(d.Before, raw.Before...)
	d.Conflicts = append(d.Conflicts, raw.Conflicts...)
	d.PartOf = append(d.PartOf, raw.PartOf...)
	d.PropagatesReloadTo = append(d.PropagatesReloadTo, raw.PropagatesReloadTo...)
	d.RequiresMountsFor = append(d.RequiresMountsFor, raw.RequiresMountsFor...)
	d.ConditionPaths = append(d.ConditionPaths, raw.ConditionPaths...)
	if raw.Reloadable != nil {
		d.Reloadable = *raw.Reloadable
	}
	if raw.RefuseManualStart != nil {
		d.RefuseManualStart = *raw.RefuseManualStart
	}
	if raw.StartSec != nil {
		d.StartSec = *raw.StartSec
	}
	if raw.StopSec != nil {
		d.StopSec = *raw.StopSec
	}
	if raw.ReloadSec != nil {
		d.ReloadSec = *raw.ReloadSec
	}
}

func finalizeDirectives(d *directives) {
	d.Requires = sortedUnique(d.Requires)
	d.Wants = sortedUnique(d.Wants)
	d.After = sortedUnique(d.After)
	d.Before = sortedUnique(d.Before)
	d.Conflicts = sortedUnique(d.Conflicts)
	d.PartOf = sortedUnique(d.PartOf)
	d.PropagatesReloadTo = sortedUnique(d.PropagatesReloadTo)
	d.RequiresMountsFor = sortedUnique(d.RequiresMountsFor)
	d.ConditionPaths = sortedUnique(d.ConditionPaths)
}

func sortedUnique(values []string) []string {
	seen := map[string]bool{}
	for _, value := range values {
		if value != "" {
			seen[value] = true
		}
	}
	out := make([]string, 0, len(seen))
	for value := range seen {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

func (s *solver) buildRelations() {
	for unit, def := range s.Defs {
		for _, other := range def.Directives.Conflicts {
			if s.Conflicts[unit] == nil {
				s.Conflicts[unit] = map[string]bool{}
			}
			if s.Conflicts[other] == nil {
				s.Conflicts[other] = map[string]bool{}
			}
			s.Conflicts[unit][other] = true
			s.Conflicts[other][unit] = true
		}
		for _, parent := range def.Directives.PartOf {
			s.PartOfReverse[parent] = append(s.PartOfReverse[parent], unit)
		}
	}
	for parent := range s.PartOfReverse {
		sort.Strings(s.PartOfReverse[parent])
	}
}

func (s *solver) buildChanges() {
	groups := map[string]*changeGroup{}
	for _, ch := range s.Input.Changes {
		if !s.ActivePaths[ch.Path] {
			s.Warnings = append(s.Warnings, warningOut{
				Code: "shadowed_change",
				Unit: ch.Unit,
				Path: ch.Path,
			})
			continue
		}
		s.DaemonReloaded = true
		if ch.Impact == "none" {
			continue
		}
		group := groups[ch.Unit]
		if group == nil {
			group = &changeGroup{Unit: ch.Unit}
			groups[ch.Unit] = group
		}
		group.Priority += ch.Priority
		if ch.Impact == "restart" {
			group.HasRestart = true
		}
		if ch.Impact == "reload" {
			group.HasReload = true
		}
	}
	sort.Slice(s.Warnings, func(i, j int) bool {
		if s.Warnings[i].Unit != s.Warnings[j].Unit {
			return s.Warnings[i].Unit < s.Warnings[j].Unit
		}
		if s.Warnings[i].Path != s.Warnings[j].Path {
			return s.Warnings[i].Path < s.Warnings[j].Path
		}
		return s.Warnings[i].Code < s.Warnings[j].Code
	})

	names := make([]string, 0, len(groups))
	for name := range groups {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		group := groups[name]
		reasons := []string{}
		if group.HasRestart {
			reasons = append(reasons, "changed_restart")
		}
		if group.HasReload {
			reasons = append(reasons, "changed_reload")
		}
		action := "reload"
		if group.HasRestart {
			action = "restart"
		}
		active := s.initialActive(name)
		if !active {
			if s.Requested[name] {
				action = "start"
				reasons = append(reasons, "requested_start")
			} else {
				s.InactiveChanged[name] = true
				continue
			}
		}
		blocked := false
		if s.Protected[name] && (action == "restart" || action == "start") {
			blocked = true
		}
		if s.Protected[name] && action == "reload" {
			if def, ok := s.Defs[name]; ok && !def.Directives.Reloadable {
				blocked = true
			}
		}
		root := rootCandidate{
			Unit:             name,
			Action:           action,
			Priority:         group.Priority,
			Reasons:          orderedReasons(sliceToSet(reasons)),
			BlockedProtected: blocked,
		}
		s.RootByUnit[name] = root
		s.Roots = append(s.Roots, root)
	}
}

func (s *solver) solve() reportOut {
	base := planState{Actions: map[string]*actionPlan{}}
	var best *candidateReport
	var visit func(int, planState)
	visit = func(idx int, current planState) {
		if idx == len(s.Roots) {
			for _, plan := range s.expandWants(current, map[string]bool{}) {
				report, ok := s.evaluate(plan)
				if !ok {
					continue
				}
				if best == nil || betterCandidate(report, *best) {
					copyReport := report
					best = &copyReport
				}
			}
			return
		}
		visit(idx+1, current.clone())
		root := s.Roots[idx]
		if root.BlockedProtected {
			return
		}
		next := current.clone()
		if changed, ok := s.addAction(next, root.Unit, root.Action, root.Reasons); ok {
			_ = changed
			visit(idx+1, next)
		}
	}
	visit(0, base)
	if best == nil {
		report, _ := s.evaluate(base)
		return report.Report
	}
	return best.Report
}

func betterCandidate(left, right candidateReport) bool {
	lo := left.Report.Objective
	ro := right.Report.Objective
	if lo.AppliedPriority != ro.AppliedPriority {
		return lo.AppliedPriority > ro.AppliedPriority
	}
	if lo.AppliedUnits != ro.AppliedUnits {
		return lo.AppliedUnits > ro.AppliedUnits
	}
	if lo.FinalActiveUnits != ro.FinalActiveUnits {
		return lo.FinalActiveUnits > ro.FinalActiveUnits
	}
	if lo.ElapsedSec != ro.ElapsedSec {
		return lo.ElapsedSec < ro.ElapsedSec
	}
	if lo.StoppedActiveUnit != ro.StoppedActiveUnit {
		return lo.StoppedActiveUnit < ro.StoppedActiveUnit
	}
	return lexLess(left.Signature, right.Signature)
}

func lexLess(left, right []string) bool {
	n := len(left)
	if len(right) < n {
		n = len(right)
	}
	for i := 0; i < n; i++ {
		if left[i] != right[i] {
			return left[i] < right[i]
		}
	}
	return len(left) < len(right)
}

func (p planState) clone() planState {
	out := planState{Actions: map[string]*actionPlan{}}
	for unit, action := range p.Actions {
		reasons := map[string]bool{}
		for reason := range action.Reasons {
			reasons[reason] = true
		}
		out.Actions[unit] = &actionPlan{Kind: action.Kind, Reasons: reasons}
	}
	return out
}

func (s *solver) expandWants(seed planState, excluded map[string]bool) []planState {
	closed, ok := s.closeMandatory(seed.clone())
	if !ok {
		return nil
	}
	wants := s.wantCandidates(closed, excluded)
	if len(wants) == 0 {
		return []planState{closed}
	}
	want := wants[0]
	excludedSkip := copyBoolMap(excluded)
	excludedSkip[want] = true
	out := s.expandWants(closed.clone(), excludedSkip)

	include := closed.clone()
	if _, ok := s.addAction(include, want, "start", []string{"wanted_dependency"}); ok {
		out = append(out, s.expandWants(include, excluded)...)
	}
	return out
}

func (s *solver) wantCandidates(plan planState, excluded map[string]bool) []string {
	candidates := map[string]bool{}
	for _, unit := range sortedActionUnits(plan) {
		action := plan.Actions[unit]
		if action.Kind == "stop" {
			continue
		}
		def, ok := s.Defs[unit]
		if !ok {
			continue
		}
		for _, want := range def.Directives.Wants {
			if excluded[want] || plan.Actions[want] != nil || s.isActiveAfter(want, plan) {
				continue
			}
			if !s.startable(want) || s.Protected[want] {
				continue
			}
			candidates[want] = true
		}
	}
	out := make([]string, 0, len(candidates))
	for unit := range candidates {
		out = append(out, unit)
	}
	sort.Strings(out)
	return out
}

func copyBoolMap(in map[string]bool) map[string]bool {
	out := map[string]bool{}
	for key, value := range in {
		out[key] = value
	}
	return out
}

func (s *solver) closeMandatory(seed planState) (planState, bool) {
	plan := seed.clone()
	changed := true
	for changed {
		changed = false
		for _, unit := range sortedActionUnits(plan) {
			action := plan.Actions[unit]
			if action.Kind == "reload" {
				def, ok := s.Defs[unit]
				if !ok {
					return plan, false
				}
				if !def.Directives.Reloadable {
					if s.Protected[unit] {
						return plan, false
					}
					if c, ok := s.addAction(plan, unit, "restart", []string{"reload_escalated"}); !ok {
						return plan, false
					} else if c {
						changed = true
					}
				}
			}
		}
		for _, unit := range sortedActionUnits(plan) {
			action := plan.Actions[unit]
			if action.Kind == "restart" {
				for _, child := range s.PartOfReverse[unit] {
					if s.initialActive(child) {
						if c, ok := s.addAction(plan, child, "restart", []string{"part_of"}); !ok {
							return plan, false
						} else if c {
							changed = true
						}
					}
				}
			}
			if action.Kind == "reload" {
				def, ok := s.Defs[unit]
				if !ok {
					return plan, false
				}
				for _, target := range def.Directives.PropagatesReloadTo {
					if s.initialActive(target) {
						if c, ok := s.addAction(plan, target, "reload", []string{"propagated_reload"}); !ok {
							return plan, false
						} else if c {
							changed = true
						}
					}
				}
			}
		}
		for _, unit := range sortedActionUnits(plan) {
			action := plan.Actions[unit]
			if action.Kind != "start" && action.Kind != "restart" {
				continue
			}
			def, ok := s.Defs[unit]
			if !ok {
				return plan, false
			}
			for _, path := range def.Directives.RequiresMountsFor {
				if s.pathExistsAfter(path, plan) {
					continue
				}
				pathInfo, ok := s.Paths[path]
				if !ok || pathInfo.MountUnit == "" {
					return plan, false
				}
				mount := pathInfo.MountUnit
				if !s.isActiveAfter(mount, plan) {
					if !s.startable(mount) || s.Protected[mount] {
						return plan, false
					}
					if c, ok := s.addAction(plan, mount, "start", []string{"requires_mounts_for"}); !ok {
						return plan, false
					} else if c {
						changed = true
					}
				}
			}
			for _, required := range def.Directives.Requires {
				if s.isActiveAfter(required, plan) {
					continue
				}
				if !s.startable(required) || s.Protected[required] {
					return plan, false
				}
				if c, ok := s.addAction(plan, required, "start", []string{"required_dependency"}); !ok {
					return plan, false
				} else if c {
					changed = true
				}
			}
		}
		for _, unit := range sortedActionUnits(plan) {
			action := plan.Actions[unit]
			if action.Kind != "start" && action.Kind != "restart" {
				continue
			}
			for conflict := range s.Conflicts[unit] {
				if !s.initialActive(conflict) {
					continue
				}
				existing := plan.Actions[conflict]
				if existing != nil {
					if existing.Kind == "stop" {
						continue
					}
					return plan, false
				}
				if s.Protected[conflict] {
					return plan, false
				}
				if c, ok := s.addAction(plan, conflict, "stop", []string{"conflict_stop"}); !ok {
					return plan, false
				} else if c {
					changed = true
				}
			}
		}
	}
	for _, unit := range sortedActionUnits(plan) {
		action := plan.Actions[unit]
		if action.Kind != "start" && action.Kind != "restart" {
			continue
		}
		def := s.Defs[unit]
		for _, path := range def.Directives.ConditionPaths {
			if !s.pathExistsAfter(path, plan) {
				return plan, false
			}
		}
	}
	return plan, true
}

func (s *solver) addAction(plan planState, unit, kind string, reasons []string) (bool, bool) {
	if kind == "start" || kind == "restart" {
		if s.Protected[unit] {
			return false, false
		}
		if !s.startable(unit) {
			return false, false
		}
	}
	if kind == "reload" {
		if _, ok := s.Defs[unit]; !ok {
			return false, false
		}
	}
	existing := plan.Actions[unit]
	if existing == nil {
		plan.Actions[unit] = &actionPlan{Kind: kind, Reasons: sliceToSet(reasons)}
		return true, true
	}
	if existing.Kind == "stop" && kind != "stop" {
		return false, false
	}
	if existing.Kind != "stop" && kind == "stop" {
		return false, false
	}
	changed := false
	if kind != "stop" && actionRank(kind) > actionRank(existing.Kind) {
		existing.Kind = kind
		changed = true
	}
	for _, reason := range reasons {
		if !existing.Reasons[reason] {
			existing.Reasons[reason] = true
			changed = true
		}
	}
	return changed, true
}

func actionRank(kind string) int {
	switch kind {
	case "start":
		return 1
	case "reload":
		return 2
	case "restart":
		return 3
	default:
		return 0
	}
}

func sliceToSet(values []string) map[string]bool {
	out := map[string]bool{}
	for _, value := range values {
		out[value] = true
	}
	return out
}

func (s *solver) evaluate(raw planState) (candidateReport, bool) {
	plan, ok := s.closeMandatory(raw.clone())
	if !ok {
		return candidateReport{}, false
	}

	appliedPriority := 0
	appliedUnits := 0
	appliedRoots := map[string]bool{}
	for unit, root := range s.RootByUnit {
		if action := plan.Actions[unit]; action != nil && rootSatisfied(root.Action, action.Kind) {
			appliedPriority += root.Priority
			appliedUnits++
			appliedRoots[unit] = true
			if _, ok := s.addAction(plan, unit, action.Kind, root.Reasons); !ok {
				return candidateReport{}, false
			}
		}
	}

	operations, signature, ok := s.operations(plan)
	if !ok {
		return candidateReport{}, false
	}
	elapsed := 0
	stoppedActive := 0
	mountStarts := 0
	for _, op := range operations {
		elapsed += op.DurationSec
		if op.Action == "stop" && s.initialActive(op.Unit) {
			stoppedActive++
		}
		if (op.Action == "start" || op.Action == "restart") && strings.HasSuffix(op.Unit, ".mount") {
			mountStarts++
		}
	}
	if elapsed > s.Input.Maintenance.DeadlineSec {
		return candidateReport{}, false
	}
	if stoppedActive > s.Input.Maintenance.MaxStoppedActive {
		return candidateReport{}, false
	}
	if mountStarts > s.Input.Maintenance.MountStartLimit {
		return candidateReport{}, false
	}

	finalActive := s.finalActiveCount(plan)
	units := s.unitRows(plan, appliedRoots)
	report := reportOut{
		DaemonReloaded: s.DaemonReloaded,
		Objective: objectiveOut{
			AppliedPriority:   appliedPriority,
			AppliedUnits:      appliedUnits,
			FinalActiveUnits:  finalActive,
			ElapsedSec:        elapsed,
			StoppedActiveUnit: stoppedActive,
		},
		Operations: operations,
		Units:      units,
		Warnings:   append([]warningOut{}, s.Warnings...),
	}
	return candidateReport{Report: report, Signature: signature}, true
}

func rootSatisfied(rootAction, actual string) bool {
	switch rootAction {
	case "restart":
		return actual == "restart"
	case "reload":
		return actual == "reload" || actual == "restart"
	case "start":
		return actual == "start" || actual == "restart"
	default:
		return false
	}
}

func (s *solver) operations(plan planState) ([]operationOut, []string, bool) {
	ops := []operationOut{}
	signature := []string{}
	step := 1
	if s.DaemonReloaded {
		ops = append(ops, operationOut{
			Step:        step,
			Action:      "daemon-reload",
			Unit:        "",
			DurationSec: s.Input.Maintenance.DaemonReloadSec,
			Reasons:     []string{"active_change"},
		})
		signature = append(signature, "daemon-reload:")
		step++
	}
	stopUnits := []string{}
	for unit, action := range plan.Actions {
		if action.Kind == "stop" {
			stopUnits = append(stopUnits, unit)
		}
	}
	sort.Strings(stopUnits)
	for _, unit := range stopUnits {
		action := plan.Actions[unit]
		ops = append(ops, operationOut{
			Step:        step,
			Action:      "stop",
			Unit:        unit,
			DurationSec: s.duration(unit, "stop"),
			Reasons:     orderedReasons(action.Reasons),
		})
		signature = append(signature, "stop:"+unit)
		step++
	}
	ordered, ok := s.topologicalActions(plan)
	if !ok {
		return nil, nil, false
	}
	for _, unit := range ordered {
		action := plan.Actions[unit]
		ops = append(ops, operationOut{
			Step:        step,
			Action:      action.Kind,
			Unit:        unit,
			DurationSec: s.duration(unit, action.Kind),
			Reasons:     orderedReasons(action.Reasons),
		})
		signature = append(signature, action.Kind+":"+unit)
		step++
	}
	return ops, signature, true
}

func (s *solver) topologicalActions(plan planState) ([]string, bool) {
	nodes := map[string]bool{}
	for unit, action := range plan.Actions {
		if action.Kind != "stop" {
			nodes[unit] = true
		}
	}
	edges := map[string]map[string]bool{}
	indegree := map[string]int{}
	for unit := range nodes {
		edges[unit] = map[string]bool{}
		indegree[unit] = 0
	}
	addEdge := func(before, after string) {
		if !nodes[before] || !nodes[after] || before == after {
			return
		}
		if !edges[before][after] {
			edges[before][after] = true
			indegree[after]++
		}
	}
	for unit := range nodes {
		def, ok := s.Defs[unit]
		if !ok {
			return nil, false
		}
		for _, after := range def.Directives.After {
			addEdge(after, unit)
		}
		for _, before := range def.Directives.Before {
			addEdge(unit, before)
		}
		for _, required := range def.Directives.Requires {
			addEdge(required, unit)
		}
		for _, path := range def.Directives.RequiresMountsFor {
			if pathInfo, ok := s.Paths[path]; ok && pathInfo.MountUnit != "" {
				addEdge(pathInfo.MountUnit, unit)
			}
		}
		for _, target := range def.Directives.PropagatesReloadTo {
			addEdge(unit, target)
		}
	}
	ready := []string{}
	for unit, degree := range indegree {
		if degree == 0 {
			ready = append(ready, unit)
		}
	}
	sort.Strings(ready)
	out := []string{}
	for len(ready) > 0 {
		unit := ready[0]
		ready = ready[1:]
		out = append(out, unit)
		nexts := make([]string, 0, len(edges[unit]))
		for next := range edges[unit] {
			nexts = append(nexts, next)
		}
		sort.Strings(nexts)
		for _, next := range nexts {
			indegree[next]--
			if indegree[next] == 0 {
				ready = append(ready, next)
				sort.Strings(ready)
			}
		}
	}
	if len(out) != len(nodes) {
		return nil, false
	}
	return out, true
}

func (s *solver) duration(unit, kind string) int {
	if kind == "daemon-reload" {
		return s.Input.Maintenance.DaemonReloadSec
	}
	def, ok := s.Defs[unit]
	if !ok {
		return 0
	}
	switch kind {
	case "start":
		return def.Directives.StartSec
	case "stop":
		return def.Directives.StopSec
	case "reload":
		return def.Directives.ReloadSec
	case "restart":
		return def.Directives.StopSec + def.Directives.StartSec
	default:
		return 0
	}
}

func (s *solver) unitRows(plan planState, appliedRoots map[string]bool) []unitOut {
	names := map[string]bool{}
	for unit := range plan.Actions {
		names[unit] = true
	}
	for unit := range s.RootByUnit {
		names[unit] = true
	}
	for unit := range s.InactiveChanged {
		names[unit] = true
	}
	sorted := make([]string, 0, len(names))
	for unit := range names {
		sorted = append(sorted, unit)
	}
	sort.Strings(sorted)
	rows := make([]unitOut, 0, len(sorted))
	for _, unit := range sorted {
		action := plan.Actions[unit]
		applied := appliedRoots[unit]
		if action != nil {
			reasons := copyReasonSet(action.Reasons)
			if root, ok := s.RootByUnit[unit]; ok && !applied && !root.BlockedProtected {
				reasons["not_selected"] = true
			}
			rows = append(rows, unitOut{
				Name:          unit,
				PlannedAction: action.Kind,
				AppliedChange: applied,
				FinalState:    s.finalState(unit, plan),
				Reasons:       orderedReasons(reasons),
			})
			continue
		}
		if root, ok := s.RootByUnit[unit]; ok {
			if root.BlockedProtected {
				rows = append(rows, unitOut{
					Name:          unit,
					PlannedAction: "unchanged",
					AppliedChange: false,
					FinalState:    s.initialFinalState(unit),
					Reasons:       []string{"protected"},
				})
			} else {
				rows = append(rows, unitOut{
					Name:          unit,
					PlannedAction: "deferred",
					AppliedChange: false,
					FinalState:    s.initialFinalState(unit),
					Reasons:       []string{"not_selected"},
				})
			}
			continue
		}
		rows = append(rows, unitOut{
			Name:          unit,
			PlannedAction: "unchanged",
			AppliedChange: false,
			FinalState:    s.initialFinalState(unit),
			Reasons:       []string{"inactive_changed"},
		})
	}
	return rows
}

func copyReasonSet(in map[string]bool) map[string]bool {
	out := map[string]bool{}
	for key, value := range in {
		out[key] = value
	}
	return out
}

func (s *solver) finalActiveCount(plan planState) int {
	units := map[string]bool{}
	for unit := range s.Defs {
		units[unit] = true
	}
	for unit := range s.Runtime {
		units[unit] = true
	}
	count := 0
	for unit := range units {
		if s.finalState(unit, plan) == "active" {
			count++
		}
	}
	return count
}

func (s *solver) finalState(unit string, plan planState) string {
	if action := plan.Actions[unit]; action != nil {
		switch action.Kind {
		case "stop":
			return "inactive"
		case "start", "reload", "restart":
			return "active"
		}
	}
	return s.initialFinalState(unit)
}

func (s *solver) initialFinalState(unit string) string {
	rt, ok := s.Runtime[unit]
	if !ok {
		return "inactive"
	}
	if rt.LoadState == "masked" {
		return "masked"
	}
	if rt.LoadState == "not-found" {
		return "not-found"
	}
	if rt.ActiveState == "" {
		return "inactive"
	}
	return rt.ActiveState
}

func (s *solver) initialActive(unit string) bool {
	rt, ok := s.Runtime[unit]
	return ok && rt.LoadState == "loaded" && rt.ActiveState == "active"
}

func (s *solver) startable(unit string) bool {
	def, ok := s.Defs[unit]
	if !ok {
		return false
	}
	if def.Directives.RefuseManualStart {
		return false
	}
	rt, ok := s.Runtime[unit]
	if !ok {
		return true
	}
	return rt.LoadState == "" || rt.LoadState == "loaded"
}

func (s *solver) isActiveAfter(unit string, plan planState) bool {
	if action := plan.Actions[unit]; action != nil {
		switch action.Kind {
		case "stop":
			return false
		case "start", "reload", "restart":
			return true
		}
	}
	return s.initialActive(unit)
}

func (s *solver) pathExistsAfter(path string, plan planState) bool {
	info, ok := s.Paths[path]
	if !ok {
		return false
	}
	if info.Exists {
		return true
	}
	return info.MountUnit != "" && s.isActiveAfter(info.MountUnit, plan)
}

func sortedActionUnits(plan planState) []string {
	out := make([]string, 0, len(plan.Actions))
	for unit := range plan.Actions {
		out = append(out, unit)
	}
	sort.Strings(out)
	return out
}

func orderedReasons(reasons map[string]bool) []string {
	out := []string{}
	known := map[string]bool{}
	for _, reason := range reasonOrder {
		if reasons[reason] {
			out = append(out, reason)
			known[reason] = true
		}
	}
	extra := []string{}
	for reason := range reasons {
		if !known[reason] {
			extra = append(extra, reason)
		}
	}
	sort.Slice(extra, func(i, j int) bool {
		ri, iok := reasonRank[extra[i]]
		rj, jok := reasonRank[extra[j]]
		if iok && jok && ri != rj {
			return ri < rj
		}
		return extra[i] < extra[j]
	})
	out = append(out, extra...)
	return out
}
