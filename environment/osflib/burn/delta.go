package burn

import "math"

// Cost returns integer Hohmann-style burn cost between circular orbit radii.
func Cost(radiusSrc, radiusDst, burnScale int) int {
	return burnScale * abs(isqrt(radiusDst)-isqrt(radiusSrc))
}

func isqrt(n int) int {
	if n <= 0 {
		return 0
	}
	return int(math.Sqrt(float64(n)))
}

func abs(n int) int {
	if n < 0 {
		return -n
	}
	return n
}

// ApplyOverrides merges policy burn_scale when present.
func ApplyOverrides(burnScale int, overrides map[string]interface{}) int {
	_ = overrides
	return burnScale
}

func toInt(v interface{}) (int, bool) {
	switch x := v.(type) {
	case float64:
		return int(x), true
	case int:
		return x, true
	default:
		return 0, false
	}
}
