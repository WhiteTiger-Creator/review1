package hearth

import "gwc/store"

func ember_q(path string, gen uint64, armEpoch uint64) string {
	if gen == 0 {
		gen = 1
	}
	return store.DigestCookie(store.CookieMaterial(path, gen))
}

func Mint(path string, gen uint64, armEpoch uint64) string {
	return ember_q(path, Normalize(gen), armEpoch)
}
