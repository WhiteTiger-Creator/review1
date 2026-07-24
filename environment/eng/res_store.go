package eng

// NewCache returns an empty epoch->band map.
func NewCache() map[int]float64 {
	return map[int]float64{}
}

// ClearCache removes every entry from cache.
func ClearCache(cache map[int]float64) {
	for k := range cache {
		delete(cache, k)
	}
}
