package record

import (
	"strings"

	"loadcrest/internal/deck"
)

func csvEscape(s string) string {
	if strings.ContainsAny(s, ",\"\r\n") {
		return `"` + strings.ReplaceAll(s, `"`, `""`) + `"`
	}
	return s
}

func num(v float64) string { return deck.FormatFloat(v) }

// CurveCSV renders curve.csv with final newline.
func CurveCSV(rows []CurveRow) []byte {
	var b strings.Builder
	b.WriteString("index,arc_length,lambda,step_size,corrector_iterations,max_power_mismatch,arc_residual,min_voltage_bus,min_voltage_pu,tangent_lambda\n")
	for _, r := range rows {
		b.WriteString(num(float64(r.Index)))
		b.WriteByte(',')
		b.WriteString(num(r.ArcLength))
		b.WriteByte(',')
		b.WriteString(num(r.Lambda))
		b.WriteByte(',')
		b.WriteString(num(r.StepSize))
		b.WriteByte(',')
		b.WriteString(num(float64(r.CorrectorIterations)))
		b.WriteByte(',')
		b.WriteString(num(r.MaxPowerMismatch))
		b.WriteByte(',')
		b.WriteString(num(r.ArcResidual))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.MinVoltageBus))
		b.WriteByte(',')
		b.WriteString(num(r.MinVoltagePU))
		b.WriteByte(',')
		b.WriteString(num(r.TangentLambda))
		b.WriteByte('\n')
	}
	return []byte(b.String())
}

// EventsCSV renders events.csv.
func EventsCSV(rows []EventRow) []byte {
	var b strings.Builder
	b.WriteString("event_index,lambda,bus_id,limit_kind,q_limit,voltage_pu\n")
	for _, r := range rows {
		b.WriteString(num(float64(r.Index)))
		b.WriteByte(',')
		b.WriteString(num(r.Lambda))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.BusID))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.Kind))
		b.WriteByte(',')
		b.WriteString(num(r.QLimit))
		b.WriteByte(',')
		b.WriteString(num(r.VoltagePU))
		b.WriteByte('\n')
	}
	return []byte(b.String())
}

// BusCSV renders critical_bus.csv.
func BusCSV(rows []BusRow) []byte {
	var b strings.Builder
	b.WriteString("bus_id,final_type,voltage_pu,angle_deg,p_generation,q_generation,p_load,q_load,voltage_state\n")
	for _, r := range rows {
		b.WriteString(csvEscape(r.BusID))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.FinalType))
		b.WriteByte(',')
		b.WriteString(num(r.VoltagePU))
		b.WriteByte(',')
		b.WriteString(num(r.AngleDeg))
		b.WriteByte(',')
		b.WriteString(num(r.PGen))
		b.WriteByte(',')
		b.WriteString(num(r.QGen))
		b.WriteByte(',')
		b.WriteString(num(r.PLoad))
		b.WriteByte(',')
		b.WriteString(num(r.QLoad))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.VoltageState))
		b.WriteByte('\n')
	}
	return []byte(b.String())
}

// BranchCSV renders critical_branch.csv.
func BranchCSV(rows []BranchRow) []byte {
	var b strings.Builder
	b.WriteString("branch_id,status,from_bus,to_bus,p_from,q_from,p_to,q_to,p_loss,q_loss\n")
	for _, r := range rows {
		b.WriteString(csvEscape(r.BranchID))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.Status))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.From))
		b.WriteByte(',')
		b.WriteString(csvEscape(r.To))
		b.WriteByte(',')
		b.WriteString(num(r.PFrom))
		b.WriteByte(',')
		b.WriteString(num(r.QFrom))
		b.WriteByte(',')
		b.WriteString(num(r.PTo))
		b.WriteByte(',')
		b.WriteString(num(r.QTo))
		b.WriteByte(',')
		b.WriteString(num(r.PLoss))
		b.WriteByte(',')
		b.WriteString(num(r.QLoss))
		b.WriteByte('\n')
	}
	return []byte(b.String())
}
