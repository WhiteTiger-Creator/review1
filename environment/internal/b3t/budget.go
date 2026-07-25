package b3t

import (
	"math"

	"basinflux/internal/f7t"
	"basinflux/internal/m7s"
	"basinflux/internal/q4c"
)

// FluxState holds the volumetric water-budget terms for one stress period.
type FluxState struct {
	PeriodID          string
	CellID            string
	PeriodDays        float64
	HeadStartM        float64
	HeadEndM          float64
	RechargeM3        float64
	EtM3              float64
	LateralM3         float64
	PumpM3            float64
	StorageChangeM3   float64
	BalanceResidualM3 float64
	EtStress          float64
	KMPerD            float64
	Sy                float64
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

// periodTerms holds the decomposed budget terms shared by coefficient
// identification and reporting evaluation.
type periodTerms struct {
	RechargeDriver float64
	EtDriver       float64
	LateralM3      float64
	StorageM3      float64
	Stress         float64
	K              float64
	Sy             float64
}

// StressFactor returns the evapotranspiration stress factor for a stress period.
//
// The SCADA snapshot is taken at period close, so the end-of-period head is the
// reference head for the stress envelope.
func StressFactor(headStartM, headEndM, wiltM, fieldM float64) float64 {
	den := fieldM - wiltM
	if math.Abs(den) < 1e-15 {
		den = 1
	}
	return clamp01((headEndM - wiltM) / den)
}

func terms(cell m7s.MeshCell, cal q4c.Coefficients, days, precipMM, petMM, headStartM, headEndM, gradient float64) periodTerms {
	k := cal.Conductivity(cell.CellID)
	sy := cal.SpecificYield(cell.CellID)
	stress := StressFactor(headStartM, headEndM, cal.WiltHeadM, cal.FieldHeadM)

	t := periodTerms{
		RechargeDriver: (precipMM / cal.DepthDivisor) * cell.AreaM2,
		EtDriver:       (petMM / cal.DepthDivisor) * cell.AreaM2 * stress,
		LateralM3:      k * cell.FaceAreaM2 * gradient * days,
		Stress:         stress,
		K:              k,
		Sy:             sy,
	}
	if cal.UseSteadyState {
		t.StorageM3 = 0
	} else {
		t.StorageM3 = cal.StorageScale * sy * cell.AreaM2 * (headEndM - headStartM)
	}
	return t
}

// IdentifyPair recovers the basin-wide recharge efficiency and crop factor from
// the calibration campaign by mass-balance inversion.
func IdentifyPair(ev m7s.Evidence, cal q4c.Coefficients) (float64, float64, error) {
	rows := make([]f7t.PairRow, 0, len(ev.Calibration))
	for _, rec := range ev.Calibration {
		cell, ok := ev.Cells[rec.CellID]
		if !ok {
			continue
		}
		t := terms(cell, cal, rec.PeriodDays, rec.PrecipMM, rec.PetMM,
			rec.HeadStartM, rec.HeadEndM, rec.HydraulicGradient)
		rows = append(rows, f7t.PairRow{
			ColA: t.RechargeDriver,
			ColB: -t.EtDriver,
			RHS:  rec.PumpM3 + t.StorageM3 - t.LateralM3,
		})
	}
	return f7t.SolvePair(rows)
}

// Evaluate computes the water-budget terms and mass-conservation residual for
// every reporting stress period.
func Evaluate(ev m7s.Evidence, cal q4c.Coefficients) []FluxState {
	out := make([]FluxState, 0, len(ev.Periods))
	for _, p := range ev.Periods {
		cell, ok := ev.Cells[p.CellID]
		if !ok {
			continue
		}
		t := terms(cell, cal, p.PeriodDays, p.PrecipMM, p.PetMM,
			p.HeadStartM, p.HeadEndM, p.HydraulicGradient)

		recharge := t.RechargeDriver * cal.RechargeEfficiency
		et := t.EtDriver * cal.CropFactor
		residual := recharge + t.LateralM3 - et - p.PumpM3 - t.StorageM3

		out = append(out, FluxState{
			PeriodID:          p.PeriodID,
			CellID:            p.CellID,
			PeriodDays:        p.PeriodDays,
			HeadStartM:        p.HeadStartM,
			HeadEndM:          p.HeadEndM,
			RechargeM3:        recharge,
			EtM3:              et,
			LateralM3:         t.LateralM3,
			PumpM3:            p.PumpM3,
			StorageChangeM3:   t.StorageM3,
			BalanceResidualM3: residual,
			EtStress:          t.Stress,
			KMPerD:            t.K,
			Sy:                t.Sy,
		})
	}
	return out
}
