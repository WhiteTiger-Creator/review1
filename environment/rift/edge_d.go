package rift

func Cleared(supp uint32, drop uint32) uint32 {
	return supp &^ drop
}

func MaskOverlap(a, b uint32) uint32 {
	return a & b
}
