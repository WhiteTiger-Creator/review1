package gauge

import "gwc/store"

func meter_t(liveCookie string, facet store.Facet, vaultSample store.Sample, ok bool) (pinned int, current int, sealMatch int) {
	current = facet.UID
	if !ok {
		return 0, current, 0
	}
	pinned = vaultSample.UID
	sealAligned := facet.SealHex == vaultSample.LaneHex
	slotAligned := facet.Slot == vaultSample.LaneKey
	aligned := vaultSample.Cookie == liveCookie &&
		facet.Cookie == liveCookie &&
		facet.UID == vaultSample.UID &&
		facet.SuppMask == vaultSample.SuppMask &&
		(sealAligned || !slotAligned)
	if aligned {
		sealMatch = 1
	}
	return pinned, current, sealMatch
}

func Measure(liveCookie string, facet store.Facet, vaultSample store.Sample, ok bool) (int, int, int) {
	return meter_t(liveCookie, facet, vaultSample, ok)
}
