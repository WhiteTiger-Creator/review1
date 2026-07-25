package m7s

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

// MeshCell is one finite-volume hydrogeologic cell of the basin discretisation.
// ArchivalKMPerD and ArchivalSy are the lab/atlas figures carried in the mesh
// export; they are descriptive metadata, not necessarily the values that the
// current aquifer-test and storage-response evidence supports.
type MeshCell struct {
	CellID        string  `json:"cell_id"`
	BasinID       string  `json:"basin_id"`
	AreaM2        float64 `json:"area_m2"`
	FaceAreaM2    float64 `json:"face_area_m2"`
	SatThicknessM float64 `json:"sat_thickness_m"`
	ArchivalK     float64 `json:"archival_k_m_per_d"`
	ArchivalSy    float64 `json:"archival_sy"`
}

// DrawdownSample is one timed drawdown reading from a constant-rate aquifer test.
type DrawdownSample struct {
	ElapsedMin           float64 `json:"elapsed_min"`
	DrawdownM            float64 `json:"drawdown_m"`
	InStraightLineWindow bool    `json:"in_straight_line_window"`
}

// AquiferTest is a constant-rate pumping test for one mesh cell.
type AquiferTest struct {
	CellID          string           `json:"cell_id"`
	BasinID         string           `json:"basin_id"`
	DischargeM3PerD float64          `json:"discharge_m3_per_d"`
	Samples         []DrawdownSample `json:"samples"`
}

// StorageRecord is one injection/head-rise pair from a storage-response trial.
type StorageRecord struct {
	InjectedVolumeM3 float64 `json:"injected_volume_m3"`
	HeadRiseM        float64 `json:"head_rise_m"`
}

// StorageResponse holds the storage-response trials for one mesh cell.
type StorageResponse struct {
	CellID  string          `json:"cell_id"`
	BasinID string          `json:"basin_id"`
	Records []StorageRecord `json:"records"`
}

// CalibrationRecord is one campaign record used for coefficient identification.
type CalibrationRecord struct {
	CampaignID        string  `json:"campaign_id"`
	CellID            string  `json:"cell_id"`
	BasinID           string  `json:"basin_id"`
	PeriodDays        float64 `json:"period_days"`
	PrecipMM          float64 `json:"precip_mm"`
	PetMM             float64 `json:"pet_mm"`
	HeadStartM        float64 `json:"head_start_m"`
	HeadEndM          float64 `json:"head_end_m"`
	HydraulicGradient float64 `json:"hydraulic_gradient"`
	PumpM3            float64 `json:"pump_m3"`
	Qualified         bool    `json:"qualified"`
}

// StressPeriod is one reporting stress period.
type StressPeriod struct {
	PeriodID          string  `json:"period_id"`
	CellID            string  `json:"cell_id"`
	BasinID           string  `json:"basin_id"`
	PeriodDays        float64 `json:"period_days"`
	PrecipMM          float64 `json:"precip_mm"`
	PetMM             float64 `json:"pet_mm"`
	HeadStartM        float64 `json:"head_start_m"`
	HeadEndM          float64 `json:"head_end_m"`
	HydraulicGradient float64 `json:"hydraulic_gradient"`
	PumpM3            float64 `json:"pump_m3"`
}

// Evidence is the complete basin evidence set assembled from the data root.
type Evidence struct {
	BasinID     string
	Cells       map[string]MeshCell
	Tests       map[string]AquiferTest
	Storage     map[string]StorageResponse
	Calibration []CalibrationRecord
	Periods     []StressPeriod
}

func jsonFiles(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".json" {
			names = append(names, filepath.Join(dir, e.Name()))
		}
	}
	sort.Strings(names)
	return names, nil
}

func decode(path string, target any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(raw, target); err != nil {
		return fmt.Errorf("%s: %w", filepath.Base(path), err)
	}
	return nil
}

// Load assembles mesh, aquifer-test, storage-response, calibration-campaign and
// reporting-period evidence from the basin data root.
func Load(dataRoot string) (Evidence, error) {
	ev := Evidence{
		Cells:   map[string]MeshCell{},
		Tests:   map[string]AquiferTest{},
		Storage: map[string]StorageResponse{},
	}

	names, err := jsonFiles(filepath.Join(dataRoot, "mesh"))
	if err != nil {
		return ev, err
	}
	for _, n := range names {
		var c MeshCell
		if err := decode(n, &c); err != nil {
			return ev, err
		}
		ev.Cells[c.CellID] = c
		ev.BasinID = c.BasinID
	}

	names, err = jsonFiles(filepath.Join(dataRoot, "aquifer_tests"))
	if err != nil {
		return ev, err
	}
	for _, n := range names {
		var t AquiferTest
		if err := decode(n, &t); err != nil {
			return ev, err
		}
		ev.Tests[t.CellID] = t
	}

	names, err = jsonFiles(filepath.Join(dataRoot, "storage_response"))
	if err != nil {
		return ev, err
	}
	for _, n := range names {
		var s StorageResponse
		if err := decode(n, &s); err != nil {
			return ev, err
		}
		ev.Storage[s.CellID] = s
	}

	names, err = jsonFiles(filepath.Join(dataRoot, "calibration"))
	if err != nil {
		return ev, err
	}
	for _, n := range names {
		var r CalibrationRecord
		if err := decode(n, &r); err != nil {
			return ev, err
		}
		ev.Calibration = append(ev.Calibration, r)
	}
	sort.Slice(ev.Calibration, func(i, j int) bool {
		return ev.Calibration[i].CampaignID < ev.Calibration[j].CampaignID
	})

	names, err = jsonFiles(filepath.Join(dataRoot, "observations"))
	if err != nil {
		return ev, err
	}
	for _, n := range names {
		var p StressPeriod
		if err := decode(n, &p); err != nil {
			return ev, err
		}
		ev.Periods = append(ev.Periods, p)
		ev.BasinID = p.BasinID
	}

	return ev, nil
}
