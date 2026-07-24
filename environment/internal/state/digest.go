package state

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"earth-neutrino-propagation/internal/physics"
)

func FromStates(configSHA string, boundary physics.Boundary, traceChain string, states []physics.FlavorState) Continuation {
	amps := Rows(states)
	return Continuation{
		SchemaVersion: 2, ConfigSHA256: configSHA, NextLayer: boundary.NextLayer, NextSubstep: boundary.NextSubstep,
		CompletedSteps: boundary.CompletedSteps, Amplitudes: amps, StateSHA256: Digest(boundary, amps), TraceChainSHA256: traceChain,
	}
}

func Rows(states []physics.FlavorState) []Amplitude {
	out := make([]Amplitude, len(states))
	for i, state := range states {
		out[i] = Amplitude{EnergyGEV: state.EnergyGEV, Electron: [2]float64{real(state.Electron), imag(state.Electron)}, Muon: [2]float64{real(state.Muon), imag(state.Muon)}}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].EnergyGEV < out[j].EnergyGEV })
	return out
}

func Digest(boundary physics.Boundary, amps []Amplitude) string {
	sorted := append([]Amplitude(nil), amps...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].EnergyGEV < sorted[j].EnergyGEV })
	var b strings.Builder
	fmt.Fprintf(&b, "boundary=%d:%d\n", boundary.NextLayer, boundary.CompletedSteps)
	for _, amp := range sorted {
		values := []float64{amp.EnergyGEV, amp.Electron[0], amp.Electron[1], amp.Muon[0], amp.Muon[1]}
		for i, value := range values {
			if i > 0 {
				b.WriteByte('|')
			}
			b.WriteString(CanonicalFloat(value))
		}
		b.WriteByte('\n')
	}
	return SHA256([]byte(b.String()))
}

func SeedTraceChain(configSHA string) string {
	return SHA256([]byte("trace-v1\nconfig=" + configSHA + "\n"))
}

func AdvanceTraceChain(previous string, globalStep int, stateDigest string) string {
	return SHA256([]byte(fmt.Sprintf("prev=%s\nstep=%d\nstate=%s\n", previous, globalStep, stateDigest)))
}

func CanonicalFloat(value float64) string {
	if value == 0 {
		return "0"
	}
	return strconv.FormatFloat(value, 'g', 17, 64)
}

func SHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
