package drive

import (
	"gwc/gauge"
	"gwc/store"
)

func MeasurePair(liveCookie string, facet store.Facet, vaultSample store.Sample, ok bool) (int, int, int) {
	return gauge.Take(liveCookie, facet, vaultSample, ok)
}
