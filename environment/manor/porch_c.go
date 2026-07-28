package manor

import "gwc/store"

func Apply(prev store.Facet, sample store.Sample, slot string) store.Facet {
	if prev.UID != 0 && prev.UID == sample.UID && prev.Cookie == sample.Cookie {
		return prev
	}
	return Publish(prev, sample, slot)
}

func HasSeal(sealHex string) bool {
	return sealHex != ""
}
