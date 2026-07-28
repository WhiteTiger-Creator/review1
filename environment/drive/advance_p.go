package drive

import (
	"gwc/rift"
	"gwc/store"
)

func HotAdvance(prev store.Sample, nextUID int, nextMark string, dropMask uint32, path string, cookie string, lane string) store.Sample {
	return rift.Advance(prev, nextUID, nextMark, dropMask, path, cookie, lane)
}
