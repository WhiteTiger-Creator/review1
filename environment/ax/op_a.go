package ax

var cfgSL float64
var cfgCuts []float64

func meanPref(tr []float64, e int) float64 {
	if e < 0 || len(tr) == 0 {
		return 0
	}
	if e >= len(tr) {
		e = len(tr) - 1
	}
	sum := 0.0
	for i := 0; i <= e; i++ {
		sum += tr[i]
	}
	return sum / float64(e + 1)
}

func rnd6(x float64) float64 {
	if x >= 0 {
		return float64(int64(x*1e6+0.5)) / 1e6
	}
	return float64(int64(x*1e6-0.5)) / 1e6
}

func clsOf(s float64) int {
	if len(cfgCuts) < 3 {
		return 3
	}
	if s >= cfgCuts[0] {
		return 0
	}
	if s >= cfgCuts[1] {
		return 1
	}
	if s >= cfgCuts[2] {
		return 2
	}
	return 3
}

func freshBand(traj []float64, e int) (float64, int) {
	raw := meanPref(traj, e) - cfgSL*float64(e)
	if raw < 0 {
		raw = 0
	}
	return rnd6(raw), clsOf(raw)
}

// SetMeta installs per-call fold parameters used by Fold and Ladder.
func SetMeta(sl float64, cuts []float64) {
	cfgSL = sl
	cfgCuts = append([]float64(nil), cuts...)
}

// Fold is the package entry used by eng for trajectory folding.
func Fold(traj []float64, cache map[int]float64, epoch int) []float64 {
	return op_a(traj, cache, epoch)
}

// Ladder returns per-epoch ladder values for a traj under current meta.
func Ladder(traj []float64, epoch int) []int {
	if epoch < 0 {
		return nil
	}
	if len(traj) == 0 {
		return []int{}
	}
	if epoch >= len(traj) {
		epoch = len(traj) - 1
	}
	out := make([]int, epoch+1)
	for e := 0; e <= epoch; e++ {
		_, c := freshBand(traj, e)
		out[e] = c
	}
	return out
}

// op_a is the fold kernel eng ultimately exercises through Fold.
func op_a(traj []float64, cache map[int]float64, epoch int) []float64 {
	if epoch < 0 {
		return nil
	}
	if len(traj) == 0 {
		return []float64{}
	}
	if epoch >= len(traj) {
		epoch = len(traj) - 1
	}
	if cache == nil {
		cache = map[int]float64{}
	}
	out := make([]float64, epoch+1)
	for e, v := range cache {
		if e >= 0 && e <= epoch {
			out[e] = v
		}
	}
	prevC := -1
	for e := 0; e <= epoch; e++ {
		b, c := freshBand(traj, e)
		if e > 0 && prevC >= 0 && c != prevC {
			for k := range cache {
				if k >= e {
					delete(cache, k)
				}
			}
			cache[e] = b
			out[e] = b
			prevC = c
			continue
		}
		if v, ok := cache[e]; ok {
			out[e] = v
			prevC = c
			continue
		}
		cache[e] = b
		out[e] = b
		prevC = c
	}
	return out
}
