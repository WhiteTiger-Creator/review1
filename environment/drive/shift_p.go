package drive

import (
	"gwc/catalog"
	"gwc/store"
)

func OpenShift(cat *store.Catalog, mark string) {
	catalog.Shift(cat, mark)
}
