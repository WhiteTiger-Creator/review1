package state

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"sort"

	"earth-neutrino-propagation/internal/physics"
)

func Load(path, configSHA string, plan physics.Plan, energies []float64) (Continuation, []physics.FlavorState, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Continuation{}, nil, err
	}
	var cp Continuation
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&cp); err != nil {
		return Continuation{}, nil, fmt.Errorf("invalid continuation: %w", err)
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return Continuation{}, nil, errors.New("invalid continuation: trailing JSON value")
	}
	boundary := physics.Boundary{NextLayer: cp.NextLayer, NextSubstep: cp.NextSubstep, CompletedSteps: cp.CompletedSteps}
	if cp.SchemaVersion != 2 || cp.ConfigSHA256 != configSHA || plan.ValidateBoundary(boundary) != nil {
		return Continuation{}, nil, errors.New("invalid continuation metadata")
	}
	if len(cp.Amplitudes) != len(energies) {
		return Continuation{}, nil, errors.New("invalid continuation energy count")
	}
	for i := 1; i < len(cp.Amplitudes); i++ {
		if cp.Amplitudes[i-1].EnergyGEV >= cp.Amplitudes[i].EnergyGEV {
			return Continuation{}, nil, errors.New("invalid continuation energy order")
		}
	}
	states := make([]physics.FlavorState, len(cp.Amplitudes))
	for i, amp := range cp.Amplitudes {
		if amp.EnergyGEV != energies[i] || !finitePair(amp.Electron) || !finitePair(amp.Muon) {
			return Continuation{}, nil, errors.New("invalid continuation amplitudes")
		}
		states[i] = physics.FlavorState{EnergyGEV: amp.EnergyGEV, Electron: complex(amp.Electron[0], amp.Electron[1]), Muon: complex(amp.Muon[0], amp.Muon[1])}
		if physics.NormError(states[i]) > 1e-9 {
			return Continuation{}, nil, errors.New("invalid continuation normalization")
		}
	}
	if cp.StateSHA256 != Digest(boundary, cp.Amplitudes) {
		return Continuation{}, nil, errors.New("invalid continuation state digest")
	}
	if len(cp.TraceChainSHA256) != 64 {
		return Continuation{}, nil, errors.New("invalid continuation trace chain")
	}
	return cp, states, nil
}

func EqualStates(a, b []physics.FlavorState, tolerance float64) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i].EnergyGEV != b[i].EnergyGEV || math.Abs(real(a[i].Electron-b[i].Electron)) > tolerance || math.Abs(imag(a[i].Electron-b[i].Electron)) > tolerance || math.Abs(real(a[i].Muon-b[i].Muon)) > tolerance || math.Abs(imag(a[i].Muon-b[i].Muon)) > tolerance {
			return false
		}
	}
	return true
}

func SortedRows(rows []Amplitude) []Amplitude {
	out := append([]Amplitude(nil), rows...)
	sort.Slice(out, func(i, j int) bool { return out[i].EnergyGEV < out[j].EnergyGEV })
	return out
}

func finitePair(v [2]float64) bool { return finite(v[0]) && finite(v[1]) }
func finite(v float64) bool        { return !math.IsNaN(v) && !math.IsInf(v, 0) }
