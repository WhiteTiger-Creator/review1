package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
)

const taskName = "boys-localization-sweep"

var caseFields = map[string]bool{
	"id": true, "dipoles": true, "frozen": true, "max_sweeps": true,
	"max_pairs_per_sweep": true, "work_budget": true, "angle_cap_rad": true,
	"min_gain": true, "gain_quantum": true, "convergence_atol": true,
	"convergence_rtol": true, "frontier_size": true,
}

type Case struct {
	ID              string        `json:"id"`
	Dipoles         [][][]float64 `json:"dipoles"`
	Frozen          []bool        `json:"frozen"`
	MaxSweeps       int           `json:"max_sweeps"`
	MaxPairs        int           `json:"max_pairs_per_sweep"`
	WorkBudget      int           `json:"work_budget"`
	AngleCap        float64       `json:"angle_cap_rad"`
	MinGain         float64       `json:"min_gain"`
	GainQuantum     float64       `json:"gain_quantum"`
	ConvergenceAtol float64       `json:"convergence_atol"`
	ConvergenceRtol float64       `json:"convergence_rtol"`
	FrontierSize    int           `json:"frontier_size"`
}

type Input struct {
	Cases []Case
}

type RotationRecord struct {
	Pair          [2]int  `json:"pair"`
	Mode          string  `json:"mode"`
	Angle         float64 `json:"angle_rad"`
	PredictedGain float64 `json:"predicted_gain"`
	GainUnits     int64   `json:"gain_units"`
	WorkCost      int     `json:"work_cost"`
}

type SweepRecord struct {
	Sweep              int              `json:"sweep"`
	Rotations          []RotationRecord `json:"rotations"`
	PlanFrontier       []FrontierRecord `json:"plan_frontier"`
	TotalPredictedGain float64          `json:"total_predicted_gain"`
	TotalGainUnits     int64            `json:"total_gain_units"`
	WorkUsed           int              `json:"work_used"`
	ObjectiveAfter     float64          `json:"objective_after"`
}

type ChoiceRecord struct {
	Pair [2]int `json:"pair"`
	Mode string `json:"mode"`
}

type FrontierRecord struct {
	Sequence       []ChoiceRecord `json:"sequence"`
	TotalGainUnits int64          `json:"total_gain_units"`
	ProposalCount  int            `json:"proposal_count"`
	WorkUsed       int            `json:"work_used"`
}

type Result struct {
	ID             string        `json:"id"`
	Transform      [][]float64   `json:"transform"`
	Centroids      [][]float64   `json:"centroids"`
	ObjectiveTrace []float64     `json:"objective_trace"`
	AcceptedSweeps []int         `json:"accepted_sweeps"`
	SweepAudit     []SweepRecord `json:"sweep_audit"`
	Checksum       float64       `json:"checksum"`
}

type Output struct {
	Results []Result `json:"results"`
}

type Proposal struct {
	i, j     int
	mode     string
	modeRank int
	angle    float64
	gain     float64
	units    int64
	workCost int
}

type Plan struct {
	items []Proposal
	units int64
	work  int
	gain  float64
}

func finite(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0)
}

func exactKeys(object map[string]json.RawMessage, expected map[string]bool) bool {
	if len(object) != len(expected) {
		return false
	}
	for key := range expected {
		if _, ok := object[key]; !ok {
			return false
		}
	}
	return true
}

func rejectDuplicateNames(raw []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var parseValue func() error
	parseValue = func() error {
		token, err := decoder.Token()
		if err != nil {
			return err
		}
		delim, ok := token.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := make(map[string]bool)
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return err
				}
				key, ok := keyToken.(string)
				if !ok {
					return errors.New("object member name is not a string")
				}
				if seen[key] {
					return fmt.Errorf("duplicate object member %q", key)
				}
				seen[key] = true
				if err := parseValue(); err != nil {
					return err
				}
			}
			closing, err := decoder.Token()
			if err != nil || closing != json.Delim('}') {
				return errors.New("invalid object closing delimiter")
			}
		case '[':
			for decoder.More() {
				if err := parseValue(); err != nil {
					return err
				}
			}
			closing, err := decoder.Token()
			if err != nil || closing != json.Delim(']') {
				return errors.New("invalid array closing delimiter")
			}
		default:
			return errors.New("unexpected closing delimiter")
		}
		return nil
	}
	if err := parseValue(); err != nil {
		return err
	}
	if _, err := decoder.Token(); err != io.EOF {
		if err == nil {
			return errors.New("extra JSON value")
		}
		return err
	}
	return nil
}

func requireEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return errors.New("extra JSON value")
		}
		return err
	}
	return nil
}

func decodeInput(raw []byte) (Input, error) {
	if err := rejectDuplicateNames(raw); err != nil {
		return Input{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	var top map[string]json.RawMessage
	if err := decoder.Decode(&top); err != nil {
		return Input{}, err
	}
	if err := requireEOF(decoder); err != nil {
		return Input{}, err
	}
	if !exactKeys(top, map[string]bool{"task": true, "cases": true}) {
		return Input{}, errors.New("input must contain exactly task and cases")
	}
	var task string
	if err := json.Unmarshal(top["task"], &task); err != nil || task != taskName {
		return Input{}, errors.New("invalid task name")
	}
	var rawCases []json.RawMessage
	if err := json.Unmarshal(top["cases"], &rawCases); err != nil || len(rawCases) == 0 {
		return Input{}, errors.New("cases must be a nonempty array")
	}
	input := Input{Cases: make([]Case, 0, len(rawCases))}
	seen := make(map[string]bool)
	for _, rawCase := range rawCases {
		var object map[string]json.RawMessage
		if err := json.Unmarshal(rawCase, &object); err != nil || !exactKeys(object, caseFields) {
			return Input{}, errors.New("case fields do not match the contract")
		}
		var item Case
		caseDecoder := json.NewDecoder(bytes.NewReader(rawCase))
		caseDecoder.DisallowUnknownFields()
		if err := caseDecoder.Decode(&item); err != nil {
			return Input{}, err
		}
		if err := validateCase(item); err != nil {
			return Input{}, fmt.Errorf("case %q: %w", item.ID, err)
		}
		if seen[item.ID] {
			return Input{}, fmt.Errorf("duplicate case id %q", item.ID)
		}
		seen[item.ID] = true
		input.Cases = append(input.Cases, item)
	}
	return input, nil
}

func validateCase(item Case) error {
	if item.ID == "" {
		return errors.New("id must be nonempty")
	}
	if len(item.Dipoles) != 3 {
		return errors.New("dipoles must contain exactly three matrices")
	}
	n := len(item.Dipoles[0])
	if n < 2 || n > 20 || len(item.Frozen) != n {
		return errors.New("invalid orbital or frozen-vector dimension")
	}
	for coordinate, matrix := range item.Dipoles {
		if len(matrix) != n {
			return fmt.Errorf("dipole matrix %d has invalid row count", coordinate)
		}
		for row := range matrix {
			if len(matrix[row]) != n {
				return fmt.Errorf("dipole matrix %d is not square", coordinate)
			}
			for column, value := range matrix[row] {
				if !finite(value) || math.Abs(value) > 1000 {
					return errors.New("dipole entries must be finite and in range")
				}
				if column < row && value != matrix[column][row] {
					return errors.New("dipole matrices must be symmetric")
				}
			}
		}
	}
	if item.MaxSweeps < 1 || item.MaxSweeps > 20 {
		return errors.New("max_sweeps must be from one through twenty")
	}
	maxPairs := n / 2
	if item.MaxPairs < 1 || item.MaxPairs > maxPairs {
		return errors.New("max_pairs_per_sweep is out of range")
	}
	if item.WorkBudget < 1 || item.WorkBudget > 2*item.MaxPairs {
		return errors.New("work_budget is out of range")
	}
	controls := []float64{item.AngleCap, item.MinGain, item.GainQuantum,
		item.ConvergenceAtol, item.ConvergenceRtol}
	for _, value := range controls {
		if !finite(value) {
			return errors.New("all numerical controls must be finite")
		}
	}
	if item.AngleCap <= 0 || item.AngleCap > math.Pi/4 {
		return errors.New("angle_cap_rad is out of range")
	}
	if item.MinGain < 0 || item.MinGain > 1e9 {
		return errors.New("min_gain is out of range")
	}
	if item.GainQuantum < 1e-6 || item.GainQuantum > 1e9 {
		return errors.New("gain_quantum is out of range")
	}
	if item.ConvergenceAtol < 0 || item.ConvergenceAtol > 1e9 {
		return errors.New("convergence_atol is out of range")
	}
	if item.ConvergenceRtol < 0 || item.ConvergenceRtol > 1e6 {
		return errors.New("convergence_rtol is out of range")
	}
	if item.FrontierSize < 1 || item.FrontierSize > 5 {
		return errors.New("frontier_size must be from one through five")
	}
	return nil
}

func cloneMatrices(source [][][]float64) [][][]float64 {
	result := make([][][]float64, len(source))
	for coordinate, matrix := range source {
		result[coordinate] = make([][]float64, len(matrix))
		for row := range matrix {
			result[coordinate][row] = append([]float64(nil), matrix[row]...)
		}
	}
	return result
}

func identity(size int) [][]float64 {
	result := make([][]float64, size)
	for row := range result {
		result[row] = make([]float64, size)
		result[row][row] = 1
	}
	return result
}

func pairGain(matrices [][][]float64, i, j int, angle float64) float64 {
	ct := math.Cos(angle)
	st := math.Sin(angle)
	ct2 := ct * ct
	st2 := st * st
	twocs := 2 * ct * st
	gain := 0.0
	for coordinate := 0; coordinate < 3; coordinate++ {
		matrix := matrices[coordinate]
		dii := matrix[i][i]
		djj := matrix[j][j]
		dij := matrix[i][j]
		newII := ct2*dii + twocs*dij + st2*djj
		newJJ := st2*dii - twocs*dij + ct2*djj
		gain += newII*newII + newJJ*newJJ - dii*dii - djj*djj
	}
	return gain
}

func appendProposal(result []Proposal, item Case, i, j int, mode string, modeRank int, angle float64, cost int) ([]Proposal, error) {
	gain := pairGain(item.Dipoles, i, j, angle)
	if !finite(gain) {
		return nil, errors.New("non-finite proposal gain")
	}
	ratio := gain/item.GainQuantum + 0.5
	if !finite(ratio) || ratio > 9e15 {
		return nil, errors.New("proposal gain units are out of range")
	}
	units := int64(math.Floor(ratio))
	if gain > item.MinGain && units >= 1 {
		result = append(result, Proposal{i: i, j: j, mode: mode, modeRank: modeRank,
			angle: angle, gain: gain, units: units, workCost: cost})
	}
	return result, nil
}

func proposalsFor(item Case, matrices [][][]float64) ([]Proposal, error) {
	working := item
	working.Dipoles = matrices
	result := make([]Proposal, 0)
	for i := 0; i < len(item.Frozen); i++ {
		if item.Frozen[i] {
			continue
		}
		for j := i + 1; j < len(item.Frozen); j++ {
			if item.Frozen[j] {
				continue
			}
			a, b, cross := 0.0, 0.0, 0.0
			for coordinate := 0; coordinate < 3; coordinate++ {
				matrix := matrices[coordinate]
				x := (matrix[i][i] - matrix[j][j]) / 2
				y := matrix[i][j]
				a += x * x
				b += y * y
				cross += x * y
			}
			angle := 0.0
			if a != b || cross != 0 {
				angle = 0.25 * math.Atan2(2*cross, a-b)
			}
			if angle >= math.Pi/4 {
				angle -= math.Pi / 2
			}
			var err error
			if math.Abs(angle) <= item.AngleCap {
				result, err = appendProposal(result, working, i, j, "direct", 0, angle, 1)
			} else {
				cappedAngle := math.Copysign(item.AngleCap, angle)
				result, err = appendProposal(result, working, i, j, "capped", 1, cappedAngle, 1)
				if err == nil {
					result, err = appendProposal(result, working, i, j, "full", 2, angle, 2)
				}
			}
			if err != nil {
				return nil, err
			}
		}
	}
	return result, nil
}

func betterPlan(candidate, incumbent Plan) bool {
	if candidate.units != incumbent.units {
		return candidate.units > incumbent.units
	}
	if len(candidate.items) != len(incumbent.items) {
		return len(candidate.items) > len(incumbent.items)
	}
	if candidate.work != incumbent.work {
		return candidate.work < incumbent.work
	}
	for index := range candidate.items {
		left := candidate.items[index]
		right := incumbent.items[index]
		if left.i != right.i {
			return left.i < right.i
		}
		if left.j != right.j {
			return left.j < right.j
		}
		if left.modeRank != right.modeRank {
			return left.modeRank < right.modeRank
		}
	}
	return false
}

func samePlan(left, right Plan) bool {
	if len(left.items) != len(right.items) {
		return false
	}
	for index := range left.items {
		if left.items[index].i != right.items[index].i ||
			left.items[index].j != right.items[index].j ||
			left.items[index].modeRank != right.items[index].modeRank {
			return false
		}
	}
	return true
}

func insertRanked(frontier []Plan, candidate Plan, limit int) []Plan {
	for _, existing := range frontier {
		if samePlan(existing, candidate) {
			return frontier
		}
	}
	position := len(frontier)
	for index, existing := range frontier {
		if betterPlan(candidate, existing) {
			position = index
			break
		}
	}
	frontier = append(frontier, Plan{})
	copy(frontier[position+1:], frontier[position:])
	frontier[position] = candidate
	if len(frontier) > limit {
		frontier = frontier[:limit]
	}
	return frontier
}

func choosePlans(item Case, proposals []Proposal) []Plan {
	type state struct {
		mask      uint32
		pairsLeft int
		workLeft  int
	}

	byFirst := make([][]Proposal, len(item.Frozen))
	var activeMask uint32
	for orbital, frozen := range item.Frozen {
		if !frozen {
			activeMask |= uint32(1) << orbital
		}
	}
	for _, proposal := range proposals {
		byFirst[proposal.i] = append(byFirst[proposal.i], proposal)
	}

	memo := make(map[state][]Plan)
	var solve func(uint32, int, int) []Plan
	solve = func(mask uint32, pairsLeft, workLeft int) []Plan {
		if mask == 0 || pairsLeft == 0 || workLeft == 0 {
			return []Plan{{items: make([]Proposal, 0)}}
		}
		key := state{mask: mask, pairsLeft: pairsLeft, workLeft: workLeft}
		if cached, ok := memo[key]; ok {
			return cached
		}

		first := 0
		for mask&(uint32(1)<<first) == 0 {
			first++
		}
		firstBit := uint32(1) << first
		best := append([]Plan(nil), solve(mask&^firstBit, pairsLeft, workLeft)...)
		for _, proposal := range byFirst[first] {
			secondBit := uint32(1) << proposal.j
			if mask&secondBit == 0 || proposal.workCost > workLeft {
				continue
			}
			suffixes := solve(mask&^firstBit&^secondBit, pairsLeft-1, workLeft-proposal.workCost)
			for _, suffix := range suffixes {
				items := make([]Proposal, 1, 1+len(suffix.items))
				items[0] = proposal
				items = append(items, suffix.items...)
				candidate := Plan{
					items: items,
					units: proposal.units + suffix.units,
					work:  proposal.workCost + suffix.work,
					gain:  proposal.gain + suffix.gain,
				}
				best = insertRanked(best, candidate, item.FrontierSize)
			}
		}
		memo[key] = best
		return best
	}

	return solve(activeMask, item.MaxPairs, item.WorkBudget)
}

func frontierRecord(plan Plan) FrontierRecord {
	sequence := make([]ChoiceRecord, 0, len(plan.items))
	for _, proposal := range plan.items {
		sequence = append(sequence, ChoiceRecord{
			Pair: [2]int{proposal.i, proposal.j},
			Mode: proposal.mode,
		})
	}
	return FrontierRecord{
		Sequence: sequence, TotalGainUnits: plan.units,
		ProposalCount: len(plan.items), WorkUsed: plan.work,
	}
}

func applyRotation(matrices [][][]float64, transform [][]float64, proposal Proposal) {
	i, j := proposal.i, proposal.j
	ct := math.Cos(proposal.angle)
	st := math.Sin(proposal.angle)
	ct2 := ct * ct
	st2 := st * st
	for coordinate := 0; coordinate < 3; coordinate++ {
		old := matrices[coordinate]
		next := make([][]float64, len(old))
		for row := range old {
			next[row] = append([]float64(nil), old[row]...)
		}
		dii := old[i][i]
		djj := old[j][j]
		dij := old[i][j]
		next[i][i] = ct2*dii + 2*ct*st*dij + st2*djj
		next[j][j] = st2*dii - 2*ct*st*dij + ct2*djj
		next[i][j] = (ct2-st2)*dij + ct*st*(djj-dii)
		next[j][i] = next[i][j]
		for k := range old {
			if k == i || k == j {
				continue
			}
			newIK := ct*old[i][k] + st*old[j][k]
			newJK := -st*old[i][k] + ct*old[j][k]
			next[i][k], next[k][i] = newIK, newIK
			next[j][k], next[k][j] = newJK, newJK
		}
		matrices[coordinate] = next
	}
	for row := range transform {
		oldI := transform[row][i]
		oldJ := transform[row][j]
		transform[row][i] = ct*oldI + st*oldJ
		transform[row][j] = -st*oldI + ct*oldJ
	}
}

func objective(matrices [][][]float64) float64 {
	result := 0.0
	for coordinate := 0; coordinate < 3; coordinate++ {
		for index := range matrices[coordinate] {
			value := matrices[coordinate][index][index]
			result += value * value
		}
	}
	return result
}

func solveCase(item Case) (Result, error) {
	matrices := cloneMatrices(item.Dipoles)
	transform := identity(len(item.Frozen))
	trace := make([]float64, 0, item.MaxSweeps+1)
	initialObjective := objective(matrices)
	if !finite(initialObjective) {
		return Result{}, errors.New("initial objective is not finite")
	}
	trace = append(trace, initialObjective)
	accepted := make([]int, 0)
	audit := make([]SweepRecord, 0, item.MaxSweeps)
	for sweep := 1; sweep <= item.MaxSweeps; sweep++ {
		proposals, err := proposalsFor(item, matrices)
		if err != nil {
			return Result{}, err
		}
		rankedPlans := choosePlans(item, proposals)
		plan := rankedPlans[0]
		frontier := make([]FrontierRecord, 0, len(rankedPlans))
		for _, candidate := range rankedPlans {
			frontier = append(frontier, frontierRecord(candidate))
		}
		rotations := make([]RotationRecord, 0, len(plan.items))
		for _, proposal := range plan.items {
			rotations = append(rotations, RotationRecord{Pair: [2]int{proposal.i, proposal.j},
				Mode: proposal.mode, Angle: proposal.angle, PredictedGain: proposal.gain,
				GainUnits: proposal.units, WorkCost: proposal.workCost})
			applyRotation(matrices, transform, proposal)
		}
		currentObjective := objective(matrices)
		if !finite(currentObjective) || !finite(plan.gain) {
			return Result{}, errors.New("non-finite sweep result")
		}
		trace = append(trace, currentObjective)
		if plan.gain <= item.ConvergenceAtol+item.ConvergenceRtol*math.Abs(currentObjective) {
			accepted = append(accepted, sweep)
		}
		audit = append(audit, SweepRecord{Sweep: sweep, Rotations: rotations,
			PlanFrontier:       frontier,
			TotalPredictedGain: plan.gain, TotalGainUnits: plan.units,
			WorkUsed: plan.work, ObjectiveAfter: currentObjective})
	}
	centroids := make([][]float64, len(item.Frozen))
	checksum := 0.0
	for index := range centroids {
		centroids[index] = make([]float64, 3)
		for coordinate := 0; coordinate < 3; coordinate++ {
			value := matrices[coordinate][index][index]
			centroids[index][coordinate] = value
			checksum += float64((index+1)*(coordinate+1)) * value
		}
	}
	n := float64(len(transform))
	for row := range transform {
		for column, value := range transform[row] {
			checksum += float64((row+1)*(column+1)) / n * value
		}
	}
	if !finite(checksum) {
		return Result{}, errors.New("checksum is not finite")
	}
	return Result{ID: item.ID, Transform: transform, Centroids: centroids,
		ObjectiveTrace: trace, AcceptedSweeps: accepted, SweepAudit: audit,
		Checksum: checksum}, nil
}

func sameFilePath(left, right string) bool {
	leftAbsolute, leftErr := filepath.Abs(left)
	rightAbsolute, rightErr := filepath.Abs(right)
	if leftErr == nil && rightErr == nil && filepath.Clean(leftAbsolute) == filepath.Clean(rightAbsolute) {
		return true
	}
	leftInfo, leftErr := os.Stat(left)
	rightInfo, rightErr := os.Stat(right)
	return leftErr == nil && rightErr == nil && os.SameFile(leftInfo, rightInfo)
}

func writeOutput(path string, output Output) error {
	temporary, err := os.CreateTemp(filepath.Dir(path), ".boys-localization-*")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	keep := false
	defer func() {
		if !keep {
			_ = os.Remove(temporaryPath)
		}
	}()
	encoder := json.NewEncoder(temporary)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(output); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return err
	}
	keep = true
	return nil
}

func run(args []string) error {
	if len(args) != 2 {
		return errors.New("usage: boys-localization-sweep INPUT OUTPUT")
	}
	if sameFilePath(args[0], args[1]) {
		return errors.New("output path must not refer to input")
	}
	raw, err := os.ReadFile(args[0])
	if err != nil {
		return err
	}
	input, err := decodeInput(raw)
	if err != nil {
		return err
	}
	output := Output{Results: make([]Result, 0, len(input.Cases))}
	for _, item := range input.Cases {
		result, err := solveCase(item)
		if err != nil {
			return fmt.Errorf("case %q: %w", item.ID, err)
		}
		output.Results = append(output.Results, result)
	}
	return writeOutput(args[1], output)
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
