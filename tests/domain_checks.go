package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"math/cmplx"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

const tolerance = 2e-12

type layer struct {
	LengthKM         float64  `json:"length_km"`
	DensityGCM3      *float64 `json:"density_g_cm3,omitempty"`
	DensityStartGCM3 *float64 `json:"density_start_g_cm3,omitempty"`
	DensityEndGCM3   *float64 `json:"density_end_g_cm3,omitempty"`
	ElectronFraction float64  `json:"electron_fraction"`
}

type config struct {
	SchemaVersion   int       `json:"schema_version"`
	MixingAngleRad  float64   `json:"mixing_angle_rad"`
	DeltaM2EV2      float64   `json:"delta_m2_ev2"`
	MaxPhaseStepRad *float64  `json:"max_phase_step_rad,omitempty"`
	EnergiesGEV     []float64 `json:"energies_gev"`
	Layers          []layer   `json:"layers"`
}

type boundary struct{ NextLayer, NextSubstep, CompletedSteps int }
type step struct {
	Global, Layer, Substep, Count int
	Length, Density, Ye           float64
}
type vector struct {
	Energy float64
	E, Mu  complex128
}

type amplitude struct {
	EnergyGEV float64    `json:"energy_gev"`
	Electron  [2]float64 `json:"electron"`
	Muon      [2]float64 `json:"muon"`
}

type continuation struct {
	SchemaVersion    int         `json:"schema_version"`
	ConfigSHA256     string      `json:"config_sha256"`
	NextLayer        int         `json:"next_layer"`
	NextSubstep      int         `json:"next_substep"`
	CompletedSteps   int         `json:"completed_steps"`
	Amplitudes       []amplitude `json:"amplitudes"`
	StateSHA256      string      `json:"state_sha256"`
	TraceChainSHA256 string      `json:"trace_chain_sha256"`
}

type energyRow struct {
	EnergyGEV float64    `json:"energy_gev"`
	Electron  [2]float64 `json:"electron"`
	Muon      [2]float64 `json:"muon"`
	PE        float64    `json:"p_e"`
	PMu       float64    `json:"p_mu"`
	NormError float64    `json:"norm_error"`
}

type traceRow struct {
	GlobalStep          int     `json:"global_step"`
	LayerIndex          int     `json:"layer_index"`
	SubstepIndex        int     `json:"substep_index"`
	SubstepCount        int     `json:"substep_count"`
	MidpointDensityGCM3 float64 `json:"midpoint_density_g_cm3"`
	MaxNormError        float64 `json:"max_norm_error"`
	StateSHA256         string  `json:"state_sha256"`
	ChainSHA256         string  `json:"chain_sha256"`
}

type propagation struct {
	SchemaVersion         int         `json:"schema_version"`
	ConfigSHA256          string      `json:"config_sha256"`
	StartLayer            int         `json:"start_layer"`
	StartSubstep          int         `json:"start_substep"`
	StartCompletedSteps   int         `json:"start_completed_steps"`
	EndLayer              int         `json:"end_layer"`
	EndSubstep            int         `json:"end_substep"`
	CompletedSteps        int         `json:"completed_steps"`
	CompletedLayers       int         `json:"completed_layers"`
	FinalStateSHA256      string      `json:"final_state_sha256"`
	FinalTraceChainSHA256 string      `json:"final_trace_chain_sha256"`
	Energies              []energyRow `json:"energies"`
	Trace                 []traceRow  `json:"trace"`
}

type reproducibility struct {
	SchemaVersion         int    `json:"schema_version"`
	ConfigSHA256          string `json:"config_sha256"`
	Mode                  string `json:"mode"`
	StartLayer            int    `json:"start_layer"`
	StartSubstep          int    `json:"start_substep"`
	StartCompletedSteps   int    `json:"start_completed_steps"`
	EndLayer              int    `json:"end_layer"`
	EndSubstep            int    `json:"end_substep"`
	CompletedSteps        int    `json:"completed_steps"`
	PropagationSHA256     string `json:"propagation_sha256"`
	ContinuationSHA256    string `json:"continuation_sha256"`
	FinalStateSHA256      string `json:"final_state_sha256"`
	FinalTraceChainSHA256 string `json:"final_trace_chain_sha256"`
}

type outputs struct {
	Propagation                                               propagation
	Continuation                                              continuation
	Reproducibility                                           reproducibility
	PropagationBytes, ContinuationBytes, ReproducibilityBytes []byte
}

type referenceResult struct {
	States   []vector
	Trace    []traceRow
	Boundary boundary
	Chain    string
}

func main() {
	bin := flag.String("bin", "", "solver binary")
	scenario := flag.String("scenario", "all", "scenario name")
	flag.Parse()
	if *bin == "" {
		fatal(errors.New("-bin is required"))
	}
	scenarios := map[string]func(string) error{
		"constant-density": scenarioConstantDensity,
		"density-ramp":     scenarioDensityRamp,
		"continuation":     scenarioContinuationEquivalence,
		"energy-order":     scenarioEnergyOrder,
		"physical-inputs":  scenarioPhysicalInputs,
		"preservation":     scenarioResultPreservation,
		"terminal":         scenarioTerminalContinuation,
		"generated":        scenarioGeneratedMantles,
		"earth-reference":  scenarioEarthReference,
		"layer-boundary":   scenarioLayerBoundary,
	}
	if *scenario != "all" {
		fn, ok := scenarios[*scenario]
		if !ok {
			fatal(fmt.Errorf("unknown scenario %q", *scenario))
		}
		if err := fn(*bin); err != nil {
			fatal(err)
		}
		fmt.Println("ok", *scenario)
		return
	}
	names := make([]string, 0, len(scenarios))
	for name := range scenarios {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		if err := scenarios[name](*bin); err != nil {
			fatal(fmt.Errorf("%s: %w", name, err))
		}
		fmt.Println("ok", name)
	}
}

func scenarioConstantDensity(bin string) error {
	d := 3.4
	cfg := config{SchemaVersion: 1, MixingAngleRad: 0.59, DeltaM2EV2: 0.00248, EnergiesGEV: []float64{3.2, 0.7, 1.4}, Layers: []layer{{LengthKM: 0, DensityGCM3: ptr(d), ElectronFraction: 0.5}, {LengthKM: 460, DensityGCM3: ptr(d), ElectronFraction: 0.49}}}
	out, raw, err := executeConfig(bin, cfg, nil)
	if err != nil {
		return err
	}
	return verify(cfg, raw, 0, -1, "fresh", out)
}

func scenarioDensityRamp(bin string) error {
	cfg := baseRampConfig()
	out, raw, err := executeConfig(bin, cfg, nil)
	if err != nil {
		return err
	}
	if err := verify(cfg, raw, 0, -1, "fresh", out); err != nil {
		return err
	}
	if len(out.Propagation.Trace) < 8 {
		return errors.New("ramp case did not produce enough substeps")
	}
	return nil
}

func scenarioLayerBoundary(bin string) error {
	cfg := baseRampConfig()
	stop := 3
	out, raw, err := executeConfig(bin, cfg, []string{"--stop-after", strconv.Itoa(stop)})
	if err != nil {
		return err
	}
	plan := buildPlan(cfg)
	wantStop := layerEnds(plan, len(cfg.Layers))[stop]
	if out.Propagation.CompletedSteps != wantStop || out.Propagation.CompletedLayers != stop {
		return errors.New("physical-layer stop did not land on the planned boundary")
	}
	return verify(cfg, raw, 0, wantStop, "fresh", out)
}

func scenarioContinuationEquivalence(bin string) error {
	cfg := baseRampConfig()
	full, raw, err := executeConfig(bin, cfg, nil)
	if err != nil {
		return err
	}
	plan := buildPlan(cfg)
	boundaries := []int{1, len(plan) / 3, len(plan) / 2, len(plan) - 1}
	for _, stop := range boundaries {
		dir, _ := os.MkdirTemp("", "nuosc-restart-")
		defer os.RemoveAll(dir)
		cfgPath := filepath.Join(dir, "config.json")
		if err := os.WriteFile(cfgPath, raw, 0o644); err != nil {
			return err
		}
		partialPaths := outputPaths(filepath.Join(dir, "partial"))
		if _, err := runSolver(bin, cfgPath, partialPaths, "", []string{"--stop-after-steps", strconv.Itoa(stop)}); err != nil {
			return err
		}
		partial, err := readOutputs(partialPaths)
		if err != nil {
			return err
		}
		if err := verify(cfg, raw, 0, stop, "fresh", partial); err != nil {
			return err
		}
		resumedPaths := outputPaths(filepath.Join(dir, "resumed"))
		if _, err := runSolver(bin, cfgPath, resumedPaths, partialPaths.Continuation, nil); err != nil {
			return err
		}
		resumed, err := readOutputs(resumedPaths)
		if err != nil {
			return err
		}
		if err := verify(cfg, raw, stop, -1, "resume", resumed); err != nil {
			return err
		}
		if full.Propagation.FinalStateSHA256 != resumed.Propagation.FinalStateSHA256 || full.Propagation.FinalTraceChainSHA256 != resumed.Propagation.FinalTraceChainSHA256 || !equalFlavorOutcomes(full.Propagation.Energies, resumed.Propagation.Energies) {
			return fmt.Errorf("resume mismatch at step %d", stop)
		}
	}
	return nil
}

func scenarioEnergyOrder(bin string) error {
	cfgA := baseRampConfig()
	cfgB := cfgA
	cfgB.EnergiesGEV = []float64{cfgA.EnergiesGEV[2], cfgA.EnergiesGEV[0], cfgA.EnergiesGEV[3], cfgA.EnergiesGEV[1]}
	outA, rawA, err := executeConfig(bin, cfgA, nil)
	if err != nil {
		return err
	}
	outB, rawB, err := executeConfig(bin, cfgB, nil)
	if err != nil {
		return err
	}
	if !equalFlavorOutcomes(outA.Propagation.Energies, outB.Propagation.Energies) {
		return errors.New("energy shuffle changed physical results")
	}
	if outA.Propagation.ConfigSHA256 == outB.Propagation.ConfigSHA256 || outA.Propagation.ConfigSHA256 != sha(rawA) || outB.Propagation.ConfigSHA256 != sha(rawB) {
		return errors.New("configuration identity is not exact-byte based")
	}
	padded := append([]byte(" \n"), rawA...)
	dir, _ := os.MkdirTemp("", "nuosc-bytes-")
	defer os.RemoveAll(dir)
	cfgPath := filepath.Join(dir, "config.json")
	if err := os.WriteFile(cfgPath, padded, 0o644); err != nil {
		return err
	}
	paths := outputPaths(dir)
	if _, err := runSolver(bin, cfgPath, paths, "", nil); err != nil {
		return err
	}
	outPad, err := readOutputs(paths)
	if err != nil {
		return err
	}
	if outPad.Propagation.ConfigSHA256 != sha(padded) || outPad.Propagation.ConfigSHA256 == outA.Propagation.ConfigSHA256 {
		return errors.New("leading whitespace was excluded from configuration identity")
	}
	return nil
}

func scenarioPhysicalInputs(bin string) error {
	cfg := baseRampConfig()
	dir, _ := os.MkdirTemp("", "nuosc-invalid-")
	defer os.RemoveAll(dir)
	paths := outputPaths(dir)
	for _, p := range []string{paths.Propagation, paths.Continuation, paths.Reproducibility} {
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(p, []byte("sentinel\n"), 0o644); err != nil {
			return err
		}
	}
	before := snapshotPaths(paths)
	invalids := [][]byte{
		[]byte(`{"schema_version":2,"mixing_angle_rad":0.5,"delta_m2_ev2":0.0024,"max_phase_step_rad":0.4,"energies_gev":[1],"layers":[],"extra":1}`),
		[]byte(`{"schema_version":2,"mixing_angle_rad":0.5,"delta_m2_ev2":0.0024,"energies_gev":[1],"layers":[]}`),
		[]byte(`{"schema_version":2,"mixing_angle_rad":0.5,"delta_m2_ev2":0.0024,"max_phase_step_rad":0.4,"energies_gev":[1,1],"layers":[]}`),
		[]byte(`{"schema_version":2,"mixing_angle_rad":0.5,"delta_m2_ev2":0.0024,"max_phase_step_rad":0.4,"energies_gev":[1],"layers":[]} {}`),
	}
	for i, raw := range invalids {
		cfgPath := filepath.Join(dir, fmt.Sprintf("bad-%d.json", i))
		_ = os.WriteFile(cfgPath, append(raw, '\n'), 0o644)
		if _, err := runSolver(bin, cfgPath, paths, "", nil); err == nil {
			return fmt.Errorf("invalid configuration %d was accepted", i)
		}
		if !sameSnapshot(before, snapshotPaths(paths)) {
			return errors.New("invalid configuration replaced existing results")
		}
	}
	valid, raw, err := executeConfig(bin, cfg, []string{"--stop-after-steps", "2"})
	if err != nil {
		return err
	}
	mutations := []func(*continuation){
		func(cp *continuation) { cp.NextSubstep++ },
		func(cp *continuation) { cp.StateSHA256 = strings.Repeat("0", 64) },
		func(cp *continuation) { cp.TraceChainSHA256 = strings.Repeat("1", 64) },
		func(cp *continuation) { cp.Amplitudes[0], cp.Amplitudes[1] = cp.Amplitudes[1], cp.Amplitudes[0] },
	}
	cfgPath := filepath.Join(dir, "valid.json")
	_ = os.WriteFile(cfgPath, raw, 0o644)
	for i, mutate := range mutations {
		cp := valid.Continuation
		cp.Amplitudes = append([]amplitude(nil), cp.Amplitudes...)
		mutate(&cp)
		badPath := filepath.Join(dir, fmt.Sprintf("badcp-%d.json", i))
		encoded, _ := json.MarshalIndent(cp, "", "  ")
		_ = os.WriteFile(badPath, append(encoded, '\n'), 0o644)
		if _, err := runSolver(bin, cfgPath, paths, badPath, nil); err == nil {
			return fmt.Errorf("invalid continuation %d was accepted", i)
		}
		if !sameSnapshot(before, snapshotPaths(paths)) {
			return errors.New("invalid continuation replaced existing results")
		}
	}
	return nil
}

func scenarioResultPreservation(bin string) error {
	cfg := baseRampConfig()
	dir, _ := os.MkdirTemp("", "nuosc-result-set-")
	defer os.RemoveAll(dir)
	cfgPath, raw, err := writeConfig(dir, cfg)
	if err != nil {
		return err
	}
	_ = raw
	paths := outputPaths(dir)
	oldReport, oldContinuation := []byte("old-propagation\n"), []byte("old-continuation\n")
	_ = os.WriteFile(paths.Propagation, oldReport, 0o644)
	_ = os.WriteFile(paths.Continuation, oldContinuation, 0o644)
	if err := os.MkdirAll(paths.Reproducibility, 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(paths.Reproducibility, "keep"), []byte("x"), 0o644); err != nil {
		return err
	}
	if _, err := runSolver(bin, cfgPath, paths, "", nil); err == nil {
		return errors.New("directory reproducibility target did not fail")
	}
	gotReport, _ := os.ReadFile(paths.Propagation)
	gotContinuation, _ := os.ReadFile(paths.Continuation)
	if !bytes.Equal(gotReport, oldReport) || !bytes.Equal(gotContinuation, oldContinuation) {
		return errors.New("incomplete result publication did not preserve the earlier scientific set")
	}
	if _, err := os.Stat(filepath.Join(paths.Reproducibility, "keep")); err != nil {
		return errors.New("reproducibility directory was altered")
	}
	matches, _ := filepath.Glob(filepath.Join(dir, ".*.tmp-*"))
	backups, _ := filepath.Glob(filepath.Join(dir, ".*.bak-*"))
	if len(matches)+len(backups) != 0 {
		return errors.New("publication left temporary or backup files")
	}
	return nil
}

func scenarioTerminalContinuation(bin string) error {
	cfg := baseRampConfig()
	full, raw, err := executeConfig(bin, cfg, nil)
	if err != nil {
		return err
	}
	dir, _ := os.MkdirTemp("", "nuosc-noop-")
	defer os.RemoveAll(dir)
	cfgPath := filepath.Join(dir, "config.json")
	_ = os.WriteFile(cfgPath, raw, 0o644)
	resumePath := filepath.Join(dir, "resume.json")
	_ = os.WriteFile(resumePath, full.ContinuationBytes, 0o644)
	paths := outputPaths(dir)
	if _, err := runSolver(bin, cfgPath, paths, resumePath, nil); err != nil {
		return err
	}
	first, err := readOutputs(paths)
	if err != nil {
		return err
	}
	if len(first.Propagation.Trace) != 0 || first.Propagation.StartCompletedSteps != first.Propagation.CompletedSteps {
		return errors.New("completed resume was not a no-op")
	}
	if _, err := runSolver(bin, cfgPath, paths, paths.Continuation, nil); err != nil {
		return err
	}
	second, err := readOutputs(paths)
	if err != nil {
		return err
	}
	if !bytes.Equal(first.PropagationBytes, second.PropagationBytes) || !bytes.Equal(first.ContinuationBytes, second.ContinuationBytes) || !bytes.Equal(first.ReproducibilityBytes, second.ReproducibilityBytes) {
		return errors.New("repeated completed resume was not byte stable")
	}
	return nil
}

func scenarioGeneratedMantles(bin string) error {
	rng := rand.New(rand.NewSource(982451653))
	for caseIndex := 0; caseIndex < 6; caseIndex++ {
		phase := 0.18 + rng.Float64()*0.35
		cfg := config{SchemaVersion: 2, MixingAngleRad: 0.32 + rng.Float64()*0.55, DeltaM2EV2: 0.0018 + rng.Float64()*0.0012, MaxPhaseStepRad: &phase}
		for i := 0; i < 4; i++ {
			cfg.EnergiesGEV = append(cfg.EnergiesGEV, 0.45+rng.Float64()*5.5)
		}
		for i := 0; i < 4+rng.Intn(3); i++ {
			start, end := rng.Float64()*9, rng.Float64()*9
			length := rng.Float64() * 1500
			if i == 1 && caseIndex%2 == 0 {
				length = 0
			}
			cfg.Layers = append(cfg.Layers, layer{LengthKM: length, DensityStartGCM3: ptr(start), DensityEndGCM3: ptr(end), ElectronFraction: 0.35 + rng.Float64()*0.3})
		}
		out, raw, err := executeConfig(bin, cfg, nil)
		if err != nil {
			return fmt.Errorf("generated %d: %w", caseIndex, err)
		}
		if err := verify(cfg, raw, 0, -1, "fresh", out); err != nil {
			return fmt.Errorf("generated %d: %w", caseIndex, err)
		}
		plan := buildPlan(cfg)
		stop := 1 + rng.Intn(len(plan)-1)
		dir, _ := os.MkdirTemp("", "nuosc-gen-resume-")
		defer os.RemoveAll(dir)
		cfgPath := filepath.Join(dir, "config.json")
		_ = os.WriteFile(cfgPath, raw, 0o644)
		partialPaths := outputPaths(filepath.Join(dir, "p"))
		_, err = runSolver(bin, cfgPath, partialPaths, "", []string{"--stop-after-steps", strconv.Itoa(stop)})
		if err != nil {
			return err
		}
		resumedPaths := outputPaths(filepath.Join(dir, "r"))
		_, err = runSolver(bin, cfgPath, resumedPaths, partialPaths.Continuation, nil)
		if err != nil {
			return err
		}
		resumed, err := readOutputs(resumedPaths)
		if err != nil {
			return err
		}
		if out.Propagation.FinalStateSHA256 != resumed.Propagation.FinalStateSHA256 || out.Propagation.FinalTraceChainSHA256 != resumed.Propagation.FinalTraceChainSHA256 {
			return fmt.Errorf("generated resume %d diverged", caseIndex)
		}
	}
	return nil
}

func scenarioEarthReference(bin string) error {
	if _, err := os.Stat("/app/fixtures/earth_mantle_profile.json"); err != nil {
		return fmt.Errorf("default fixture unavailable: %w", err)
	}
	dir, _ := os.MkdirTemp("", "nuosc-default-")
	defer os.RemoveAll(dir)
	paths := outputPaths(dir)
	args := []string{"--propagation", paths.Propagation, "--continuation", paths.Continuation, "--reproducibility", paths.Reproducibility}
	cmd := exec.Command(bin, args...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("default configuration failed: %w: %s", err, strings.TrimSpace(string(out)))
	}
	result, err := readOutputs(paths)
	if err != nil {
		return err
	}
	raw, _ := os.ReadFile("/app/fixtures/earth_mantle_profile.json")
	var cfg config
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return err
	}
	return verify(cfg, raw, 0, -1, "fresh", result)
}

func verify(cfg config, raw []byte, start, stop int, mode string, out outputs) error {
	plan := buildPlan(cfg)
	if stop < 0 {
		stop = len(plan)
	}
	configSHA := sha(raw)
	ref := reference(cfg, plan, stop, configSHA)
	startBoundary := boundaryAt(plan, len(cfg.Layers), start)
	if out.Propagation.SchemaVersion != 2 || out.Continuation.SchemaVersion != 2 || out.Reproducibility.SchemaVersion != 1 {
		return errors.New("schema version mismatch")
	}
	if out.Propagation.ConfigSHA256 != configSHA || out.Continuation.ConfigSHA256 != configSHA || out.Reproducibility.ConfigSHA256 != configSHA {
		return errors.New("configuration SHA mismatch")
	}
	if out.Propagation.StartLayer != startBoundary.NextLayer || out.Propagation.StartSubstep != startBoundary.NextSubstep || out.Propagation.StartCompletedSteps != start {
		return errors.New("propagation start boundary mismatch")
	}
	if out.Propagation.EndLayer != ref.Boundary.NextLayer || out.Propagation.EndSubstep != ref.Boundary.NextSubstep || out.Propagation.CompletedSteps != stop || out.Propagation.CompletedLayers != ref.Boundary.NextLayer {
		return errors.New("propagation end boundary mismatch")
	}
	if out.Continuation.NextLayer != ref.Boundary.NextLayer || out.Continuation.NextSubstep != ref.Boundary.NextSubstep || out.Continuation.CompletedSteps != stop {
		return errors.New("continuation boundary mismatch")
	}
	if out.Reproducibility.Mode != mode || out.Reproducibility.StartLayer != startBoundary.NextLayer || out.Reproducibility.StartSubstep != startBoundary.NextSubstep || out.Reproducibility.StartCompletedSteps != start || out.Reproducibility.EndLayer != ref.Boundary.NextLayer || out.Reproducibility.EndSubstep != ref.Boundary.NextSubstep || out.Reproducibility.CompletedSteps != stop {
		return errors.New("reproducibility boundary mismatch")
	}
	if len(out.Propagation.Energies) != len(ref.States) || len(out.Continuation.Amplitudes) != len(ref.States) {
		return errors.New("energy count mismatch")
	}
	for i, want := range ref.States {
		got := out.Propagation.Energies[i]
		amp := out.Continuation.Amplitudes[i]
		if got.EnergyGEV != want.Energy || amp.EnergyGEV != want.Energy {
			return errors.New("energy order mismatch")
		}
		if cmplx.Abs(pair(got.Electron)-want.E) > tolerance || cmplx.Abs(pair(got.Muon)-want.Mu) > tolerance || cmplx.Abs(pair(amp.Electron)-want.E) > tolerance || cmplx.Abs(pair(amp.Muon)-want.Mu) > tolerance {
			return fmt.Errorf("amplitude mismatch at %.17g", want.Energy)
		}
		pe, pm := abs2(want.E), abs2(want.Mu)
		norm := math.Abs(pe + pm - 1)
		if math.Abs(got.PE-pe) > tolerance || math.Abs(got.PMu-pm) > tolerance || math.Abs(got.NormError-norm) > tolerance || got.NormError > 1e-12 {
			return fmt.Errorf("probability mismatch at %.17g", want.Energy)
		}
	}
	wantDigest := stateDigest(ref.Boundary, amplitudes(ref.States))
	if out.Propagation.FinalStateSHA256 != wantDigest || out.Continuation.StateSHA256 != wantDigest || out.Reproducibility.FinalStateSHA256 != wantDigest {
		return errors.New("final state digest mismatch")
	}
	if out.Propagation.FinalTraceChainSHA256 != ref.Chain || out.Continuation.TraceChainSHA256 != ref.Chain || out.Reproducibility.FinalTraceChainSHA256 != ref.Chain {
		return errors.New("trace chain mismatch")
	}
	if len(out.Propagation.Trace) != stop-start {
		return errors.New("trace length mismatch")
	}
	for i, want := range ref.Trace[start:stop] {
		got := out.Propagation.Trace[i]
		if got.GlobalStep != want.GlobalStep || got.LayerIndex != want.LayerIndex || got.SubstepIndex != want.SubstepIndex || got.SubstepCount != want.SubstepCount || math.Abs(got.MidpointDensityGCM3-want.MidpointDensityGCM3) > tolerance || math.Abs(got.MaxNormError-want.MaxNormError) > tolerance || got.StateSHA256 != want.StateSHA256 || got.ChainSHA256 != want.ChainSHA256 {
			return fmt.Errorf("trace mismatch at global step %d", want.GlobalStep)
		}
	}
	if out.Reproducibility.PropagationSHA256 != sha(out.PropagationBytes) || out.Reproducibility.ContinuationSHA256 != sha(out.ContinuationBytes) {
		return errors.New("reproducibility byte hash mismatch")
	}
	if !oneFinalNewline(out.PropagationBytes) || !oneFinalNewline(out.ContinuationBytes) || !oneFinalNewline(out.ReproducibilityBytes) || bytes.Contains(out.PropagationBytes, []byte("\t")) {
		return errors.New("JSON byte format mismatch")
	}
	return nil
}

func reference(cfg config, plan []step, stop int, configSHA string) referenceResult {
	energies := append([]float64(nil), cfg.EnergiesGEV...)
	sort.Float64s(energies)
	states := make([]vector, len(energies))
	for i, energy := range energies {
		states[i] = vector{Energy: energy, E: 1}
	}
	return referenceWithSHA(cfg, plan, stop, states, configSHA)
}

func referenceWithSHA(cfg config, plan []step, stop int, states []vector, configSHA string) referenceResult {
	chain := seedChain(configSHA)
	trace := make([]traceRow, 0, stop)
	for index := 0; index < stop; index++ {
		st := plan[index]
		for i := range states {
			apply(&states[i], cfg, st)
		}
		b := boundaryAt(plan, len(cfg.Layers), index+1)
		digest := stateDigest(b, amplitudes(states))
		chain = advanceChain(chain, index, digest)
		trace = append(trace, traceRow{GlobalStep: index, LayerIndex: st.Layer, SubstepIndex: st.Substep, SubstepCount: st.Count, MidpointDensityGCM3: st.Density, MaxNormError: maxNorm(states), StateSHA256: digest, ChainSHA256: chain})
	}
	return referenceResult{States: states, Trace: trace, Boundary: boundaryAt(plan, len(cfg.Layers), stop), Chain: chain}
}

func buildPlan(cfg config) []step {
	steps := []step{}
	for li, l := range cfg.Layers {
		count := 1
		if cfg.SchemaVersion == 2 && l.LengthKM != 0 {
			maxPhase := 0.0
			for _, energy := range cfg.EnergiesGEV {
				for _, density := range []float64{*l.DensityStartGCM3, *l.DensityEndGCM3} {
					value := phase(cfg, energy, l.LengthKM, density, l.ElectronFraction)
					if value > maxPhase {
						maxPhase = value
					}
				}
			}
			count = int(math.Ceil(maxPhase / *cfg.MaxPhaseStepRad))
			if count < 1 {
				count = 1
			}
		}
		start, end := densityBounds(cfg, l)
		for si := 0; si < count; si++ {
			fraction := (float64(si) + 0.5) / float64(count)
			density := start + (end-start)*fraction
			steps = append(steps, step{Global: len(steps), Layer: li, Substep: si, Count: count, Length: l.LengthKM / float64(count), Density: density, Ye: l.ElectronFraction})
		}
	}
	return steps
}

func phase(cfg config, energy, length, density, ye float64) float64 {
	s, c := math.Sin(2*cfg.MixingAngleRad), math.Cos(2*cfg.MixingAngleRad)
	a := 7.56e-5 * density * ye * energy / cfg.DeltaM2EV2
	d := math.Hypot(s, c-a)
	return math.Abs(1.267 * cfg.DeltaM2EV2 * length * d / energy)
}

func apply(v *vector, cfg config, st step) {
	if st.Length == 0 {
		return
	}
	s, c := math.Sin(2*cfg.MixingAngleRad), math.Cos(2*cfg.MixingAngleRad)
	a := 7.56e-5 * st.Density * st.Ye * v.Energy / cfg.DeltaM2EV2
	d := math.Hypot(s, c-a)
	phi := 1.267 * cfg.DeltaM2EV2 * st.Length * d / v.Energy
	nx, nz := s/d, (a-c)/d
	co, si := math.Cos(phi), math.Sin(phi)
	oldE, oldMu := v.E, v.Mu
	v.E = complex(co, -si*nz)*oldE + complex(0, -si*nx)*oldMu
	v.Mu = complex(0, -si*nx)*oldE + complex(co, si*nz)*oldMu
}

func executeConfig(bin string, cfg config, extra []string) (outputs, []byte, error) {
	dir, err := os.MkdirTemp("", "nuosc-case-")
	if err != nil {
		return outputs{}, nil, err
	}
	defer os.RemoveAll(dir)
	cfgPath, raw, err := writeConfig(dir, cfg)
	if err != nil {
		return outputs{}, nil, err
	}
	paths := outputPaths(dir)
	if _, err := runSolver(bin, cfgPath, paths, "", extra); err != nil {
		return outputs{}, nil, err
	}
	out, err := readOutputs(paths)
	if err != nil {
		return outputs{}, nil, err
	}
	return out, raw, nil
}

type paths struct{ Propagation, Continuation, Reproducibility string }

func outputPaths(dir string) paths {
	return paths{filepath.Join(dir, "propagation.json"), filepath.Join(dir, "continuation.json"), filepath.Join(dir, "reproducibility.json")}
}

func runSolver(bin, cfgPath string, p paths, resume string, extra []string) ([]byte, error) {
	args := []string{"--config", cfgPath, "--propagation", p.Propagation, "--continuation", p.Continuation, "--reproducibility", p.Reproducibility}
	if resume != "" {
		args = append(args, "--resume", resume)
	}
	args = append(args, extra...)
	cmd := exec.Command(bin, args...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return out, fmt.Errorf("solver failed: %w: %s", err, strings.TrimSpace(string(out)))
	}
	return out, nil
}

func readOutputs(p paths) (outputs, error) {
	var out outputs
	var err error
	if out.PropagationBytes, err = os.ReadFile(p.Propagation); err != nil {
		return out, err
	}
	if out.ContinuationBytes, err = os.ReadFile(p.Continuation); err != nil {
		return out, err
	}
	if out.ReproducibilityBytes, err = os.ReadFile(p.Reproducibility); err != nil {
		return out, err
	}
	if err = strictJSON(out.PropagationBytes, &out.Propagation); err != nil {
		return out, err
	}
	if err = strictJSON(out.ContinuationBytes, &out.Continuation); err != nil {
		return out, err
	}
	if err = strictJSON(out.ReproducibilityBytes, &out.Reproducibility); err != nil {
		return out, err
	}
	return out, nil
}

func strictJSON(raw []byte, dst any) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return err
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		if err == nil {
			return errors.New("trailing JSON value")
		}
		return err
	}
	return nil
}
func writeConfig(dir string, cfg config) (string, []byte, error) {
	raw, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return "", nil, err
	}
	raw = append(raw, '\n')
	path := filepath.Join(dir, "config.json")
	return path, raw, os.WriteFile(path, raw, 0o644)
}

func baseRampConfig() config {
	phase := 0.31
	return config{SchemaVersion: 2, MixingAngleRad: 0.583, DeltaM2EV2: 0.00245, MaxPhaseStepRad: &phase, EnergiesGEV: []float64{2.4, 0.65, 4.8, 1.25}, Layers: []layer{
		{LengthKM: 180, DensityStartGCM3: ptr(0), DensityEndGCM3: ptr(0), ElectronFraction: 0.5},
		{LengthKM: 0, DensityStartGCM3: ptr(2.7), DensityEndGCM3: ptr(4.1), ElectronFraction: 0.49},
		{LengthKM: 620, DensityStartGCM3: ptr(2.8), DensityEndGCM3: ptr(2.8), ElectronFraction: 0.5},
		{LengthKM: 1340, DensityStartGCM3: ptr(3.0), DensityEndGCM3: ptr(8.1), ElectronFraction: 0.47},
		{LengthKM: 910, DensityStartGCM3: ptr(8.4), DensityEndGCM3: ptr(3.6), ElectronFraction: 0.46},
	}}
}

func densityBounds(cfg config, l layer) (float64, float64) {
	if cfg.SchemaVersion == 1 {
		return *l.DensityGCM3, *l.DensityGCM3
	}
	return *l.DensityStartGCM3, *l.DensityEndGCM3
}
func layerEnds(plan []step, layerCount int) []int {
	ends := make([]int, layerCount+1)
	for _, s := range plan {
		ends[s.Layer+1] = s.Global + 1
	}
	for i := 1; i < len(ends); i++ {
		if ends[i] == 0 {
			ends[i] = ends[i-1]
		}
	}
	return ends
}
func boundaryAt(plan []step, layerCount, completed int) boundary {
	if completed == len(plan) {
		return boundary{layerCount, 0, completed}
	}
	s := plan[completed]
	return boundary{s.Layer, s.Substep, completed}
}
func amplitudes(states []vector) []amplitude {
	out := make([]amplitude, len(states))
	for i, s := range states {
		out[i] = amplitude{s.Energy, [2]float64{real(s.E), imag(s.E)}, [2]float64{real(s.Mu), imag(s.Mu)}}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].EnergyGEV < out[j].EnergyGEV })
	return out
}
func stateDigest(b boundary, amps []amplitude) string {
	sorted := append([]amplitude(nil), amps...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].EnergyGEV < sorted[j].EnergyGEV })
	var s strings.Builder
	fmt.Fprintf(&s, "boundary=%d:%d:%d\n", b.NextLayer, b.NextSubstep, b.CompletedSteps)
	for _, a := range sorted {
		vals := []float64{a.EnergyGEV, a.Electron[0], a.Electron[1], a.Muon[0], a.Muon[1]}
		for i, v := range vals {
			if i > 0 {
				s.WriteByte('|')
			}
			s.WriteString(canonical(v))
		}
		s.WriteByte('\n')
	}
	return sha([]byte(s.String()))
}
func seedChain(configSHA string) string { return sha([]byte("trace-v1\nconfig=" + configSHA + "\n")) }
func advanceChain(prev string, step int, digest string) string {
	return sha([]byte(fmt.Sprintf("prev=%s\nstep=%d\nstate=%s\n", prev, step, digest)))
}
func canonical(v float64) string {
	if v == 0 {
		return "0"
	}
	return strconv.FormatFloat(v, 'g', 17, 64)
}
func maxNorm(states []vector) float64 {
	m := 0.0
	for _, s := range states {
		e := math.Abs(abs2(s.E) + abs2(s.Mu) - 1)
		if e > m {
			m = e
		}
	}
	return m
}
func abs2(v complex128) float64    { return real(v)*real(v) + imag(v)*imag(v) }
func pair(v [2]float64) complex128 { return complex(v[0], v[1]) }
func ptr(v float64) *float64       { return &v }
func sha(b []byte) string          { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }
func oneFinalNewline(b []byte) bool {
	return len(b) > 0 && b[len(b)-1] == '\n' && (len(b) == 1 || b[len(b)-2] != '\n')
}
func equalFlavorOutcomes(a, b []energyRow) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i].EnergyGEV != b[i].EnergyGEV || cmplx.Abs(pair(a[i].Electron)-pair(b[i].Electron)) > tolerance || cmplx.Abs(pair(a[i].Muon)-pair(b[i].Muon)) > tolerance {
			return false
		}
	}
	return true
}
func snapshotPaths(p paths) map[string][]byte {
	out := map[string][]byte{}
	for _, path := range []string{p.Propagation, p.Continuation, p.Reproducibility} {
		out[path], _ = os.ReadFile(path)
	}
	return out
}
func sameSnapshot(a, b map[string][]byte) bool {
	if len(a) != len(b) {
		return false
	}
	for k, v := range a {
		if !bytes.Equal(v, b[k]) {
			return false
		}
	}
	return true
}
func fatal(err error) { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
