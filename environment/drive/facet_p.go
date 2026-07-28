package drive

import (
	"gwc/manor"
	"gwc/store"
)

func PublishFacet(prev store.Facet, sample store.Sample, slot string) store.Facet {
	return manor.Apply(prev, sample, slot)
}
