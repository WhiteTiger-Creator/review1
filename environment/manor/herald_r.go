package manor

import "gwc/store"

func herald_r(prev store.Facet, sample store.Sample, slot string) store.Facet {
	out := store.Facet{
		UID:      sample.UID,
		SuppMask: sample.SuppMask,
		Cookie:   sample.Cookie,
		SealHex:  sample.LaneHex,
		Mark:     sample.Mark,
		Slot:     slot,
	}
	if prev.Mark != "" && prev.Mark != sample.Mark {
		out.Slot = sample.LaneKey
	} else if out.Slot == "" {
		out.Slot = sample.LaneKey
	}
	return out
}

func Publish(prev store.Facet, sample store.Sample, slot string) store.Facet {
	return herald_r(prev, sample, slot)
}
