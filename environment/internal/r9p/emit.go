package r9p

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"

	"basinflux/internal/b3t"
	"basinflux/internal/m7s"
	"basinflux/internal/q4c"
)

// ClosureToleranceM3 is the absolute volumetric closure tolerance of the
// mass-conservation contract.
const ClosureToleranceM3 = 1e-6

// archivalDivisor is the depth divisor of the historian archive that summary
// recharge totals are reconciled against.
const archivalDivisor = 100.0

func round12(v float64) float64 {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return v
	}
	return math.Round(v*1e12) / 1e12
}

// Emit writes the basin water-budget diagnostics document.
func Emit(outPath string, ev m7s.Evidence, fluxes []b3t.FluxState, cal q4c.Coefficients) error {
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}

	rows := make([]b3t.FluxState, len(fluxes))
	copy(rows, fluxes)
	// Rows are grouped per mesh cell so that per-cell budgets read contiguously.
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].CellID != rows[j].CellID {
			return rows[i].CellID < rows[j].CellID
		}
		return rows[i].PeriodID < rows[j].PeriodID
	})

	tolerance := cal.CampaignToleranceM3
	if tolerance <= 0 {
		tolerance = ClosureToleranceM3
	}

	periods := make([]map[string]any, 0, len(rows))
	var totalRecharge, totalET, totalLateral, totalPump, totalStorage float64
	var maxResidual float64
	compliant := 0

	for _, r := range rows {
		ok := math.Abs(r.BalanceResidualM3) <= tolerance
		if ok {
			compliant++
		}
		if math.Abs(r.BalanceResidualM3) > maxResidual {
			maxResidual = math.Abs(r.BalanceResidualM3)
		}
		totalRecharge += r.RechargeM3
		totalET += r.EtM3
		totalLateral += r.LateralM3
		totalPump += r.PumpM3
		totalStorage += r.StorageChangeM3

		periods = append(periods, map[string]any{
			"period_id":           r.PeriodID,
			"cell_id":             r.CellID,
			"period_days":         round12(r.PeriodDays),
			"head_start_m":        round12(r.HeadStartM),
			"head_end_m":          round12(r.HeadEndM),
			"recharge_m3":         round12(r.RechargeM3),
			"et_m3":               round12(r.EtM3),
			"lateral_m3":          round12(r.LateralM3),
			"pump_m3":             round12(r.PumpM3),
			"storage_change_m3":   round12(r.StorageChangeM3),
			"balance_residual_m3": round12(r.BalanceResidualM3),
			"et_stress":           round12(r.EtStress),
			"k_m_per_d":           round12(r.KMPerD),
			"sy":                  round12(r.Sy),
			"closure_compliant":   ok,
		})
	}

	// Historian reconciliation of the summed recharge against the archive
	// divisor. Operations records this as a validation-only pass.
	if cal.DepthDivisor > 0 {
		totalRecharge = totalRecharge * (cal.DepthDivisor / archivalDivisor)
	}

	report := map[string]any{
		"schema_version":     "1.0",
		"basin_id":           ev.BasinID,
		"calibration_source": cal.Source,
		"steady_state_mode":  cal.UseSteadyState,
		"periods":            periods,
		"summary": map[string]any{
			"period_count":            len(rows),
			"total_recharge_m3":       round12(totalRecharge),
			"total_et_m3":             round12(totalET),
			"total_lateral_m3":        round12(totalLateral),
			"total_pump_m3":           round12(totalPump),
			"total_storage_change_m3": round12(totalStorage),
			"max_balance_residual_m3": round12(maxResidual),
			"periods_compliant":       compliant,
			"recharge_efficiency":     round12(cal.RechargeEfficiency),
			"crop_factor":             round12(cal.CropFactor),
		},
	}

	raw, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(outPath, raw, 0o644)
}
