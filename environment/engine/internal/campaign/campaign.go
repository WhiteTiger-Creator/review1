package campaign

import "sort"

type Weights struct {
	Infrastructure     int `json:"infrastructure"`
	Civilian           int `json:"civilian"`
	FalseAlarmPenalty  int `json:"false_alarm_penalty"`
	SyncCapture        int `json:"sync_capture"`
	BreakthroughPenalty int `json:"breakthrough_penalty"`
	IntegrityBonus     int `json:"integrity_bonus"`
}

func DefaultWeights() Weights {
	return Weights{
		Infrastructure:      10,
		Civilian:            5,
		FalseAlarmPenalty:   3,
		SyncCapture:         8,
		BreakthroughPenalty: 15,
		IntegrityBonus:      4,
	}
}

type State struct {
	Weights          Weights
	InfrastructureHP int
	CiviliansSafe    int
	CiviliansTotal   int
	FalseAlarms      int
	SyncCaptures     int
	Breakthroughs    int
	GeneratorsAlive  int
	GeneratorsTotal  int
	Score            int
}

func (s *State) Recompute() {
	w := s.Weights
	score := 0
	score += s.InfrastructureHP * w.Infrastructure
	score += s.CiviliansSafe * w.Civilian
	score -= s.FalseAlarms * w.FalseAlarmPenalty
	score += s.SyncCaptures * w.SyncCapture
	score -= s.Breakthroughs * w.BreakthroughPenalty
	if s.GeneratorsAlive == s.GeneratorsTotal && s.GeneratorsTotal > 0 {
		score += w.IntegrityBonus
	}
	s.Score = score
}

func (s *State) Snapshot() map[string]any {
	s.Recompute()
	return map[string]any{
		"infrastructure_hp": s.InfrastructureHP,
		"civilians_safe":    s.CiviliansSafe,
		"civilians_total":   s.CiviliansTotal,
		"false_alarms":      s.FalseAlarms,
		"sync_captures":     s.SyncCaptures,
		"breakthroughs":     s.Breakthroughs,
		"generators_alive":  s.GeneratorsAlive,
		"generators_total":  s.GeneratorsTotal,
		"score":             s.Score,
		"weights": map[string]int{
			"infrastructure":       s.Weights.Infrastructure,
			"civilian":             s.Weights.Civilian,
			"false_alarm_penalty":  s.Weights.FalseAlarmPenalty,
			"sync_capture":         s.Weights.SyncCapture,
			"breakthrough_penalty": s.Weights.BreakthroughPenalty,
			"integrity_bonus":      s.Weights.IntegrityBonus,
		},
	}
}

func CorridorSectors(corridors [][]string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, c := range corridors {
		for _, s := range c {
			if !seen[s] {
				seen[s] = true
				out = append(out, s)
			}
		}
	}
	sort.Strings(out)
	return out
}
