package gauge

import "gwc/store"

func Take(liveCookie string, facet store.Facet, vaultSample store.Sample, ok bool) (int, int, int) {
	return meter_t(liveCookie, facet, vaultSample, ok)
}

func Nonzero(v int) bool {
	return v != 0
}
