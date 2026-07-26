package signal

// DebrisRoll returns a deterministic 0..99 roll from seed, tick, and craft id.
func DebrisRoll(seed, tick int, craftID string) int {
	h := 0
	for _, c := range craftID {
		h = h*31 + int(c)
	}
	x := seed*1103515245 + tick*12345 + h*17
	if x < 0 {
		x = -x
	}
	return x % 100
}

// Strike reports whether the debris roll meets or exceeds the threshold.
func Strike(roll, threshold int) bool {
	return roll < threshold
}

// RelayLost reports whether blackout was exceeded at close.
func RelayLost(tick, lastRelay, blackout int) bool {
	return tick-lastRelay >= blackout
}

// ApplySignalOverrides merges debris_threshold and comm_blackout_ticks.
func ApplySignalOverrides(debrisThreshold, blackout int, overrides map[string]interface{}) (int, int) {
	if overrides == nil {
		return debrisThreshold, blackout
	}
	if v, ok := overrides["debris_threshold"]; ok {
		if n, ok := toInt(v); ok {
			debrisThreshold = n
		}
	}
	if v, ok := overrides["comm_blackout_ticks"]; ok {
		if n, ok := toInt(v); ok && n >= 0 {
			blackout = n
		}
	}
	return debrisThreshold, blackout
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
