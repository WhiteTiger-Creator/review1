package deck

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// CanonicalNetworkText builds the POWER-10 identity deck.
func CanonicalNetworkText(n *Network) string {
	var b strings.Builder
	b.WriteString("AC_NETWORK 1\n")
	b.WriteString("BASE_MVA ")
	b.WriteString(FormatFloat(n.BaseMVA))
	b.WriteByte('\n')
	for _, bus := range n.Buses {
		b.WriteString("BUS ")
		b.WriteString(bus.ID)
		b.WriteByte(' ')
		b.WriteString(string(bus.Type))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.VSet))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.Angle))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.PGen))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.QGen))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.QMin))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.QMax))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.PLoad))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.QLoad))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.GShunt))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(bus.BShunt))
		b.WriteByte('\n')
	}
	for _, br := range n.Branches {
		b.WriteString("BRANCH ")
		b.WriteString(br.ID)
		b.WriteByte(' ')
		b.WriteString(br.From)
		b.WriteByte(' ')
		b.WriteString(br.To)
		b.WriteByte(' ')
		b.WriteString(string(br.Status))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(br.R))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(br.X))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(br.BTotal))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(br.Tap))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(br.ShiftDeg))
		b.WriteByte('\n')
	}
	b.WriteString("END\n")
	return b.String()
}

// NetworkSHA256 returns lowercase hex digest of the canonical network deck.
func NetworkSHA256(n *Network) string {
	sum := sha256.Sum256([]byte(CanonicalNetworkText(n)))
	return hex.EncodeToString(sum[:])
}

// CanonicalRampText builds the TRACE-02 identity deck.
func CanonicalRampText(r *Ramp) string {
	var b strings.Builder
	b.WriteString("AC_RAMP 1\n")
	for _, d := range r.Demands {
		b.WriteString("DEMAND ")
		b.WriteString(d.BusID)
		b.WriteByte(' ')
		b.WriteString(FormatFloat(d.DeltaP))
		b.WriteByte(' ')
		b.WriteString(FormatFloat(d.DeltaQ))
		b.WriteByte('\n')
	}
	b.WriteString("LIMITS ")
	b.WriteString(FormatFloat(r.VoltageMin))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(r.VoltageMax))
	b.WriteByte('\n')
	b.WriteString("STEPS ")
	b.WriteString(FormatFloat(r.StepInitial))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(r.StepMinimum))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(r.StepMaximum))
	b.WriteByte('\n')
	b.WriteString("TOLERANCES ")
	b.WriteString(FormatFloat(r.PowerTolerance))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(r.ArcTolerance))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(r.ReactiveEventTol))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(r.FoldTolerance))
	b.WriteByte('\n')
	b.WriteString("ITERATIONS ")
	b.WriteString(FormatFloat(float64(r.BaseMaxIterations)))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(float64(r.CorrectorMaxIters)))
	b.WriteByte(' ')
	b.WriteString(FormatFloat(float64(r.PointMax)))
	b.WriteByte('\n')
	b.WriteString("END\n")
	return b.String()
}

// RampSHA256 returns lowercase hex digest of the canonical ramp deck.
func RampSHA256(r *Ramp) string {
	sum := sha256.Sum256([]byte(CanonicalRampText(r)))
	return hex.EncodeToString(sum[:])
}
