package physics

import (
	"errors"
	"math"

	"earth-neutrino-propagation/internal/medium"
)

const matterCoefficient = 7.56e-5
const vacuumPhaseCoefficient = 1.267

type Boundary struct {
	NextLayer      int `json:"next_layer"`
	NextSubstep    int `json:"next_substep"`
	CompletedSteps int `json:"completed_steps"`
}

type Step struct {
	GlobalIndex         int
	LayerIndex          int
	SubstepIndex        int
	SubstepCount        int
	LengthKM            float64
	MidpointDensityGCM3 float64
	ElectronFraction    float64
}

type Plan struct {
	Steps         []Step
	LayerEndSteps []int
	LayerSubsteps []int
}

func BuildPlan(cfg medium.Config) Plan {
	plan := Plan{LayerEndSteps: make([]int, len(cfg.Layers)+1), LayerSubsteps: make([]int, len(cfg.Layers))}
	for layerIndex, layer := range cfg.Layers {
		count := substepCount(cfg, layer)
		plan.LayerSubsteps[layerIndex] = count
		for substep := 0; substep < count; substep++ {
			fraction := float64(substep) / float64(count)
			density := layer.DensityStartGCM3 + (layer.DensityEndGCM3-layer.DensityStartGCM3)*fraction
			plan.Steps = append(plan.Steps, Step{
				GlobalIndex: len(plan.Steps), LayerIndex: layerIndex, SubstepIndex: substep, SubstepCount: count,
				LengthKM: layer.LengthKM / float64(count), MidpointDensityGCM3: density, ElectronFraction: layer.ElectronFraction,
			})
		}
		plan.LayerEndSteps[layerIndex+1] = len(plan.Steps)
	}
	return plan
}

func substepCount(cfg medium.Config, layer medium.Layer) int {
	if cfg.SingleStep || layer.LengthKM == 0 {
		return 1
	}
	maxPhase := 0.0
	for _, energy := range cfg.EnergiesGEV {
		phase := PhaseMagnitude(cfg.MixingAngleRad, cfg.DeltaM2EV2, energy, layer.LengthKM, layer.DensityStartGCM3, layer.ElectronFraction)
		if phase > maxPhase {
			maxPhase = phase
		}
	}
	count := int(math.Ceil(maxPhase / cfg.MaxPhaseStepRad))
	if count < 1 {
		return 1
	}
	return count
}

func PhaseMagnitude(theta, deltaM2, energy, lengthKM, density, electronFraction float64) float64 {
	sin2 := math.Sin(2 * theta)
	cos2 := math.Cos(2 * theta)
	matter := matterCoefficient * density * electronFraction * energy / deltaM2
	scale := math.Hypot(sin2, cos2-matter)
	return math.Abs(vacuumPhaseCoefficient * deltaM2 * lengthKM * scale / energy)
}

func (p Plan) TotalSteps() int { return len(p.Steps) }

func (p Plan) BoundaryAt(completed int) (Boundary, error) {
	if completed < 0 || completed > len(p.Steps) {
		return Boundary{}, errors.New("invalid completed step boundary")
	}
	if completed == len(p.Steps) {
		return Boundary{NextLayer: len(p.LayerSubsteps), NextSubstep: 0, CompletedSteps: completed}, nil
	}
	step := p.Steps[completed]
	return Boundary{NextLayer: step.LayerIndex, NextSubstep: step.SubstepIndex, CompletedSteps: completed}, nil
}

func (p Plan) StepsAfterLayers(layers int) (int, error) {
	if layers < 0 || layers >= len(p.LayerEndSteps) {
		return 0, errors.New("invalid stop-after boundary")
	}
	return p.LayerEndSteps[layers], nil
}

func (p Plan) ValidateBoundary(boundary Boundary) error {
	want, err := p.BoundaryAt(boundary.CompletedSteps)
	if err != nil || want != boundary {
		return errors.New("invalid continuation boundary")
	}
	return nil
}
