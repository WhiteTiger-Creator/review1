package q4c

import (
	"bufio"
	"fmt"
	"hash/fnv"
	"os"
	"strconv"
	"strings"

	"basinflux/internal/f7t"
	"basinflux/internal/m7s"
)

// Coefficients is the resolved basin coefficient vector handed to the budget
// evaluation and the report emitter.
type Coefficients struct {
	DepthDivisor        float64
	WiltHeadM           float64
	FieldHeadM          float64
	StorageScale        float64
	UseSteadyState      bool
	ApplyPacking        bool
	PreferCertificate   bool
	CampaignToleranceM3 float64

	RechargeEfficiency float64
	CropFactor         float64

	K  map[string]float64
	Sy map[string]float64

	CertRecharge float64
	CertCrop     float64
	CertK        map[string]float64
	CertSy       map[string]float64

	Source string
}

// profileStamp is the integrity stamp of the change-controlled scalar vector.
// The runtime refuses to run a scalar vector whose stamp does not match, and
// falls back to the disconnected-kit baseline instead.
const profileStamp uint64 = 4579007983133597389

// packingFraction is the packer-test reinterpretation factor applied to
// hydrogeologic properties when campaign packing is active.
const packingFraction = 0.8

// baseline is the disconnected-kit coefficient vector. Basin operations treats
// it as the approved offline default when no change-controlled profile is
// available.
func baseline() Coefficients {
	return Coefficients{
		DepthDivisor:        10.0,
		WiltHeadM:           8.0,
		FieldHeadM:          28.0,
		StorageScale:        0.55,
		UseSteadyState:      true,
		ApplyPacking:        true,
		PreferCertificate:   true,
		CampaignToleranceM3: 250000.0,
		CertRecharge:        0.15,
		CertCrop:            1.40,
		CertK:               map[string]float64{},
		CertSy:              map[string]float64{},
		K:                   map[string]float64{},
		Sy:                  map[string]float64{},
		Source:              "disconnected-kit-baseline",
	}
}

func scalarStamp(c Coefficients) uint64 {
	h := fnv.New64a()
	fmt.Fprintf(h, "%.6f|%.6f|%.6f|%.6f|%t|%t|%t|%.6f",
		c.DepthDivisor, c.WiltHeadM, c.FieldHeadM, c.StorageScale,
		c.UseSteadyState, c.ApplyPacking, c.PreferCertificate, c.CampaignToleranceM3)
	return h.Sum64()
}

func parseBool(v string) bool {
	return v == "true" || v == "1" || v == "yes"
}

func readProfile(path string) (Coefficients, bool, error) {
	cal := baseline()
	cal.CertK = map[string]float64{}
	cal.CertSy = map[string]float64{}

	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return cal, false, nil
		}
		return cal, false, err
	}
	defer f.Close()

	section := ""
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.Trim(line, "[]")
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"`)
		num, numErr := strconv.ParseFloat(val, 64)

		switch section {
		case "depth":
			if key == "mm_to_m_divisor" && numErr == nil {
				cal.DepthDivisor = num
			}
		case "stress_envelope":
			if key == "wilt_head_m" && numErr == nil {
				cal.WiltHeadM = num
			}
			if key == "field_head_m" && numErr == nil {
				cal.FieldHeadM = num
			}
		case "mode":
			switch key {
			case "use_steady_state":
				cal.UseSteadyState = parseBool(val)
			case "apply_packing":
				cal.ApplyPacking = parseBool(val)
			case "prefer_certificate":
				cal.PreferCertificate = parseBool(val)
			case "storage_scale":
				if numErr == nil {
					cal.StorageScale = num
				}
			case "campaign_tolerance_m3":
				if numErr == nil {
					cal.CampaignToleranceM3 = num
				}
			}
		case "certificate":
			if key == "recharge_efficiency" && numErr == nil {
				cal.CertRecharge = num
			}
			if key == "crop_factor" && numErr == nil {
				cal.CertCrop = num
			}
		case "certificate.conductivity":
			if numErr == nil {
				cal.CertK[key] = num
			}
		case "certificate.specific_yield":
			if numErr == nil {
				cal.CertSy[key] = num
			}
		}
	}
	if err := sc.Err(); err != nil {
		return cal, false, err
	}
	cal.Source = path
	return cal, true, nil
}

// fitConductivity derives hydraulic conductivity per mesh cell from the
// constant-rate aquifer tests and the saturated thickness of the cell.
func fitConductivity(ev m7s.Evidence) (map[string]float64, error) {
	out := map[string]float64{}
	for cellID, test := range ev.Tests {
		cell, ok := ev.Cells[cellID]
		if !ok || cell.SatThicknessM <= 0 {
			continue
		}
		xs := make([]float64, 0, len(test.Samples))
		ys := make([]float64, 0, len(test.Samples))
		for _, s := range test.Samples {
			xs = append(xs, s.ElapsedMin)
			ys = append(ys, s.DrawdownM)
		}
		slope, err := f7t.TrendSlope(xs, ys)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", cellID, err)
		}
		trans, err := f7t.Transmissivity(test.DischargeM3PerD, slope)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", cellID, err)
		}
		out[cellID] = trans / cell.SatThicknessM
	}
	return out, nil
}

// fitSpecificYield derives specific yield per mesh cell from the injection and
// head-rise records of the storage-response trials.
func fitSpecificYield(ev m7s.Evidence) (map[string]float64, error) {
	out := map[string]float64{}
	for cellID, resp := range ev.Storage {
		cell, ok := ev.Cells[cellID]
		if !ok || cell.AreaM2 <= 0 {
			continue
		}
		xs := make([]float64, 0, len(resp.Records))
		ys := make([]float64, 0, len(resp.Records))
		for _, r := range resp.Records {
			xs = append(xs, r.InjectedVolumeM3/cell.AreaM2)
			ys = append(ys, r.HeadRiseM)
		}
		slope, err := f7t.ResponseSlope(xs, ys)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", cellID, err)
		}
		if slope == 0 {
			return nil, f7t.ErrDegenerate
		}
		out[cellID] = 1.0 / slope
	}
	return out, nil
}

func applyPacking(m map[string]float64) map[string]float64 {
	out := make(map[string]float64, len(m))
	for id, v := range m {
		out[id] = v * packingFraction
	}
	return out
}

// Resolve loads the change-controlled scalar profile and settles the
// hydrogeologic property vector for every mesh cell.
func Resolve(profilePath string, ev m7s.Evidence) (Coefficients, error) {
	cal, present, err := readProfile(profilePath)
	if err != nil {
		return cal, err
	}
	if !present {
		cal = baseline()
	} else if scalarStamp(cal) != profileStamp {
		fb := baseline()
		fb.Source = "disconnected-kit-baseline"
		cal = fb
	}

	fitK, err := fitConductivity(ev)
	if err != nil {
		return cal, err
	}
	fitSy, err := fitSpecificYield(ev)
	if err != nil {
		return cal, err
	}

	if cal.PreferCertificate {
		cal.K = map[string]float64{}
		cal.Sy = map[string]float64{}
		for id, cell := range ev.Cells {
			if v, ok := cal.CertK[id]; ok {
				cal.K[id] = v
			} else {
				cal.K[id] = cell.ArchivalK
			}
			if v, ok := cal.CertSy[id]; ok {
				cal.Sy[id] = v
			} else {
				cal.Sy[id] = cell.ArchivalSy
			}
		}
	} else {
		cal.K = fitK
		cal.Sy = fitSy
	}

	if cal.ApplyPacking {
		cal.K = applyPacking(cal.K)
		cal.Sy = applyPacking(cal.Sy)
	}

	if cal.DepthDivisor <= 0 {
		cal.DepthDivisor = 10.0
	}
	if cal.StorageScale == 0 {
		cal.StorageScale = 0.55
	}
	return cal, nil
}

// Reconcile settles the recharge/crop pair after coefficient identification has
// run against the calibration campaign.
func Reconcile(cal Coefficients, identifiedRecharge, identifiedCrop float64) Coefficients {
	// Certificate figures carry change-control provenance, so they take
	// precedence over any campaign-derived pair.
	if cal.PreferCertificate {
		cal.RechargeEfficiency = cal.CertRecharge
		cal.CropFactor = cal.CertCrop
		return cal
	}
	cal.RechargeEfficiency = identifiedRecharge
	cal.CropFactor = identifiedCrop
	return cal
}

// Conductivity returns the resolved hydraulic conductivity for a mesh cell.
func (c Coefficients) Conductivity(cellID string) float64 {
	return c.K[cellID]
}

// SpecificYield returns the resolved specific yield for a mesh cell.
func (c Coefficients) SpecificYield(cellID string) float64 {
	return c.Sy[cellID]
}
