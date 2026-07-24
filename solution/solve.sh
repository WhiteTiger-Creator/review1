#!/usr/bin/env bash
set -euo pipefail
[ -d /app/data/impressions ] || { echo "missing /app/data" >&2; exit 1; }
[ -f /app/data/serp_templates.json ] || { echo "missing serp_templates.json" >&2; exit 1; }
[ -f /app/data/extractor_releases.csv ] || { echo "missing extractor_releases.csv" >&2; exit 1; }
cd /app/rank

cat > model.go <<'GOEOF'
package main

import (
	"bufio"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type templateCfg struct {
	PageSlots int `json:"page_slots"`
	Templates []struct {
		TemplateID   string `json:"template_id"`
		OrganicSlots []int  `json:"organic_slots"`
	} `json:"templates"`
}

func loadSlotMaps(dataDir string) map[string][]int {
	out := map[string][]int{}
	b, err := os.ReadFile(filepath.Join(dataDir, "serp_templates.json"))
	if err != nil {
		return out
	}
	var cfg templateCfg
	if json.Unmarshal(b, &cfg) != nil {
		return out
	}
	for _, t := range cfg.Templates {
		out[t.TemplateID] = t.OrganicSlots
	}
	return out
}

func loadReleases(dataDir string) map[int]string {
	out := map[int]string{}
	f, err := os.Open(filepath.Join(dataDir, "extractor_releases.csv"))
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	first := true
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if first {
			first = false
			continue
		}
		if line == "" {
			continue
		}
		p := strings.Split(line, ",")
		if len(p) < 2 {
			continue
		}
		d, _ := strconv.Atoi(p[0])
		out[d] = p[1]
	}
	return out
}

func sig(z float64) float64 {
	if z >= 0 {
		return 1.0 / (1.0 + math.Exp(-z))
	}
	e := math.Exp(z)
	return e / (1.0 + e)
}

func Estimate(imprs []Impression, numFeatures, numSlots int, dataDir string) ([]float64, []float64) {
	slotMaps := loadSlotMaps(dataDir)
	releases := loadReleases(dataDir)

	N := len(imprs)
	X := make([][]float64, 0, N)
	clicks := make([]int, 0, N)
	slots := make([]int, 0, N)
	groups := make([]string, 0, N)

	for _, im := range imprs {
		sm, ok := slotMaps[im.TemplateID]
		if !ok || im.SerpRank < 1 || im.SerpRank > len(sm) {
			continue
		}
		s := sm[im.SerpRank-1] - 1
		if s < 0 || s >= numSlots {
			continue
		}
		g, ok := releases[im.SessionDay]
		if !ok {
			g = "unknown"
		}
		v := make([]float64, numFeatures)
		copy(v, im.Features)
		X = append(X, v)
		clicks = append(clicks, im.Clicked)
		slots = append(slots, s)
		groups = append(groups, g)
	}
	N = len(X)

	sum := map[string][]float64{}
	sqsum := map[string][]float64{}
	cntg := map[string]float64{}
	for i := 0; i < N; i++ {
		g := groups[i]
		if _, ok := sum[g]; !ok {
			sum[g] = make([]float64, numFeatures)
			sqsum[g] = make([]float64, numFeatures)
		}
		for k := 0; k < numFeatures; k++ {
			sum[g][k] += X[i][k]
			sqsum[g][k] += X[i][k] * X[i][k]
		}
		cntg[g]++
	}
	mean := map[string][]float64{}
	sd := map[string][]float64{}
	for g, n := range cntg {
		mean[g] = make([]float64, numFeatures)
		sd[g] = make([]float64, numFeatures)
		for k := 0; k < numFeatures; k++ {
			mu := sum[g][k] / n
			va := sqsum[g][k]/n - mu*mu
			if va < 1e-18 {
				va = 1e-18
			}
			mean[g][k] = mu
			sd[g][k] = math.Sqrt(va)
		}
	}
	for i := 0; i < N; i++ {
		g := groups[i]
		for k := 0; k < numFeatures; k++ {
			X[i][k] = (X[i][k] - mean[g][k]) / sd[g][k]
		}
	}

	theta := make([]float64, numSlots)
	cnt := make([]float64, numSlots)
	clk := make([]float64, numSlots)
	for i := 0; i < N; i++ {
		cnt[slots[i]]++
		clk[slots[i]] += float64(clicks[i])
	}
	for p := 0; p < numSlots; p++ {
		if cnt[p] > 0 {
			theta[p] = clk[p] / cnt[p]
		} else {
			theta[p] = 0.01
		}
	}
	if theta[0] <= 0 {
		theta[0] = 1.0
	}
	t0 := theta[0]
	for p := 0; p < numSlots; p++ {
		theta[p] = math.Max(1e-4, math.Min(0.999, theta[p]/t0))
	}
	theta[0] = 1.0

	w := make([]float64, numFeatures)
	b := 0.0
	lr := 0.4
	l2 := 1e-4
	emIters := 40
	innerEpochs := 25
	target := make([]float64, N)
	invN := 1.0 / float64(N)

	for it := 0; it < emIters; it++ {
		examSum := make([]float64, numSlots)
		examCnt := make([]float64, numSlots)
		for i := 0; i < N; i++ {
			z := b
			for k := 0; k < numFeatures; k++ {
				z += w[k] * X[i][k]
			}
			r := sig(z)
			th := theta[slots[i]]
			if clicks[i] == 1 {
				target[i] = 1.0
				examSum[slots[i]] += 1.0
			} else {
				denom := 1.0 - th*r
				if denom < 1e-9 {
					denom = 1e-9
				}
				examSum[slots[i]] += th * (1.0 - r) / denom
				target[i] = (1.0 - th) * r / denom
			}
			examCnt[slots[i]]++
		}
		for p := 0; p < numSlots; p++ {
			if examCnt[p] > 0 {
				theta[p] = math.Max(1e-4, math.Min(1.0, examSum[p]/examCnt[p]))
			}
		}
		t0 = theta[0]
		if t0 < 1e-6 {
			t0 = 1e-6
		}
		for p := 0; p < numSlots; p++ {
			theta[p] = math.Max(1e-4, math.Min(1.0, theta[p]/t0))
		}
		for ep := 0; ep < innerEpochs; ep++ {
			gw := make([]float64, numFeatures)
			gb := 0.0
			for i := 0; i < N; i++ {
				z := b
				for k := 0; k < numFeatures; k++ {
					z += w[k] * X[i][k]
				}
				g := sig(z) - target[i]
				for k := 0; k < numFeatures; k++ {
					gw[k] += g * X[i][k]
				}
				gb += g
			}
			for k := 0; k < numFeatures; k++ {
				w[k] -= lr * (gw[k]*invN + l2*w[k])
			}
			b -= lr * gb * invN
		}
	}
	return theta, w
}
GOEOF

go build -o /app/rank/rankbin .
mkdir -p /app/output
/app/rank/rankbin
