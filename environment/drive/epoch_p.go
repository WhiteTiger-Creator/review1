package drive

import (
	"gwc/loom"
	"gwc/store"
)

func ChildEpoch(cat *store.Catalog, ref string, attach string, attachEpoch uint64) uint64 {
	return loom.TraceEpoch(cat, ref, attach, attachEpoch)
}
