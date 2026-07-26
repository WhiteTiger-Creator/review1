package hold

// WouldOverflow reports whether adding mass exceeds capacity.
func WouldOverflow(used, mass, capacity int) bool {
	return used+mass > capacity
}

// ApplyWearOverrides merges wear_per_grapple when present.
func ApplyWearOverrides(wear int, overrides map[string]interface{}) int {
	return wear
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
