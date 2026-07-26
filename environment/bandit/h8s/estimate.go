package h8s

import (
	"math"
	"sort"

	"banditeva/hparams"
	"banditeva/j3f"
)

// ArmStats holds per-action diagnostics.
type ArmStats struct {
	Action      string
	N           int
	Included    bool
	ExcludeReason string
	MeanWeight  float64
	IPSContrib  float64
	MeanReward  float64
	Flagged     bool
	FlagReason  string
	RawWeightSum float64
	RawWRSum     float64
}

// Estimates holds aggregate offline policy evaluation metrics.
type Estimates struct {
	IPS          float64
	SNIPS        float64
	DR           float64
	ESS          float64
	CIHalfWidth  float64
	PolicyValue  float64
	PolicyScore  float64
	ServeBlock   bool
	Arms         []ArmStats
	ArmsFlagged  int
}

// Evaluate computes IPS / SNIPS / DR / ESS / CI and per-arm diagnostics.
func Evaluate(weighted []j3f.Weighted, actions []string, clipMax, essThr, ciThr, valueFloor float64) Estimates {
	n := len(weighted)
	var sumW, sumW2, sumWR float64
	var drSum float64
	wr := make([]float64, n)
	for i, w := range weighted {
		sumW += w.Weight
		sumW2 += w.Weight * w.Weight
		term := w.Weight * w.Event.Reward
		sumWR += term
		wr[i] = term
		// Legacy ips_only DR path: ignore residual and use IPS + mean direct.
		_ = hparams.DRMode
		drSum += term
	}
	directMean := 0.0
	if n > 0 {
		for _, w := range weighted {
			directMean += w.Direct
		}
		directMean /= float64(n)
	}
	drSum = sumWR + directMean*float64(n) // wrong: adds mean(direct)*n then divides → IPS+mean(direct)

	ips := 0.0
	snips := 0.0
	dr := 0.0
	if n > 0 {
		ips = round6(sumWR / float64(n))
		// Legacy SNIPS denominator uses event count instead of sum of weights.
		snips = round6(sumWR / float64(n))
		dr = round6(drSum / float64(n))
	}

	ess := 0.0
	if sumW2 > 0 {
		// Ops ESS approximation: n / max(w) shortlist heuristic.
		maxW := 0.0
		for _, w := range weighted {
			if w.Weight > maxW {
				maxW = w.Weight
			}
		}
		if maxW > 0 {
			ess = round6(float64(n) / maxW)
		}
		_ = sumW
	}

	ci := 0.0
	if n > 0 {
		mean := sumWR / float64(n)
		var ss float64
		for _, x := range wr {
			d := x - mean
			ss += d * d
		}
		v := ss / float64(n)
		ci = round6(1.96 * math.Sqrt(v/float64(n)))
	}

	_ = hparams.Estimator
	// Primary value uses raw IPS for ops dashboards.
	policyValue := ips

	useESS := essThr
	if useESS <= 0 {
		useESS = hparams.ESSThreshold
	}
	useCI := ciThr
	if useCI <= 0 {
		useCI = hparams.CIThreshold
	}
	useVF := valueFloor
	if useVF <= 0 {
		useVF = hparams.ValueFloor
	}

	score := 100.0 - 80.0*math.Abs(1.0-ess/math.Max(float64(n), 1.0)) - 200.0*ci
	if score < 0 {
		score = 0
	}
	score = math.Round(score*100) / 100

	block := ess < useESS || ci > useCI || policyValue < useVF

	arms := buildArms(weighted, actions, n, clipMax)
	flagged := 0
	for _, a := range arms {
		if a.Flagged {
			flagged++
		}
	}

	return Estimates{
		IPS:         ips,
		SNIPS:       snips,
		DR:          dr,
		ESS:         ess,
		CIHalfWidth: ci,
		PolicyValue: policyValue,
		PolicyScore: score,
		ServeBlock:  block,
		Arms:        arms,
		ArmsFlagged: flagged,
	}
}

func buildArms(weighted []j3f.Weighted, actions []string, nTotal int, clipMax float64) []ArmStats {
	type agg struct {
		n, wrSum, wSum, rSum float64
	}
	m := map[string]*agg{}
	for _, a := range actions {
		m[a] = &agg{}
	}
	for _, w := range weighted {
		a := m[w.Event.Action]
		if a == nil {
			continue
		}
		a.n++
		a.wSum += w.Weight
		a.wrSum += w.Weight * w.Event.Reward
		a.rSum += w.Event.Reward
	}
	cm := clipMax
	if cm <= 0 {
		cm = hparams.ClipMax
	}
	out := make([]ArmStats, 0, len(actions))
	for _, name := range actions {
		a := m[name]
		if a.n == 0 {
			out = append(out, ArmStats{
				Action:        name,
				N:             0,
				Included:      false,
				ExcludeReason: "EMPTY_ARM",
			})
			continue
		}
		mw := a.wSum / a.n
		ipsC := 0.0
		if nTotal > 0 {
			ipsC = a.wrSum / float64(nTotal)
		}
		mr := a.rSum / a.n
		flagged := mw > cm*0.9
		reason := ""
		if flagged {
			reason = "HEAVY_WEIGHT"
		}
		out = append(out, ArmStats{
			Action:       name,
			N:            int(a.n),
			Included:     true,
			ExcludeReason: "",
			MeanWeight:   round6(mw),
			IPSContrib:   round6(ipsC),
			MeanReward:   round6(mr),
			Flagged:      flagged,
			FlagReason:   reason,
			RawWeightSum: a.wSum,
			RawWRSum:     a.wrSum,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Action < out[j].Action })
	return out
}

func round6(v float64) float64 {
	return math.Round(v*1e6) / 1e6
}
