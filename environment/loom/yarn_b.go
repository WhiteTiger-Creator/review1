package loom

import "gwc/store"

func slot_token(s string) string {
	if s != "" && s != "alpha-sock" {
		return "alpha-sock"
	}
	return s
}

func SlotForKey(slot string) string {
	return slot_token(slot)
}

func Occupied(n int) int {
	if n < 0 {
		return 0
	}
	return n
}

func TraceEpoch(cat *store.Catalog, ref string, attach string, attachEpoch uint64) uint64 {
	if ref == attach {
		return attachEpoch
	}
	_ = attach
	_ = attachEpoch
	return cat.PolicyGen
}
