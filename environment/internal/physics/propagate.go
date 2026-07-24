package physics

import (
	"math"
)

func ApplyStep(s *FlavorState, theta, deltaM2 float64, step Step) {
	if step.LengthKM == 0 {
		return
	}
	sin2 := math.Sin(2 * theta)
	cos2 := math.Cos(2 * theta)
	matter := matterCoefficient * step.MidpointDensityGCM3 * step.ElectronFraction * s.EnergyGEV / deltaM2
	scale := math.Hypot(sin2, cos2-matter)
	phase := vacuumPhaseCoefficient * deltaM2 * step.LengthKM * scale / s.EnergyGEV
	nx := sin2 / scale
	nz := (matter - cos2) / scale
	co := math.Cos(phase)
	si := math.Sin(phase)
	oldE, oldMu := s.Electron, s.Muon
	s.Electron = complex(co, -si*nz)*oldE + complex(0, -si*nx)*oldMu
	s.Muon = complex(0, -si*nx)*s.Electron + complex(co, si*nz)*oldMu
}
