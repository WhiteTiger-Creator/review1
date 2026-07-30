package ingest

import (
	"sort"

	"wavellite_dc/q4"
)

func normalizeBundle(b *q4.Bundle) {
	sort.SliceStable(b.Units, func(i, j int) bool { return b.Units[i].ID < b.Units[j].ID })
	sort.SliceStable(b.Approvals, func(i, j int) bool {
		if b.Approvals[i].Unit != b.Approvals[j].Unit {
			return b.Approvals[i].Unit < b.Approvals[j].Unit
		}
		return b.Approvals[i].Role < b.Approvals[j].Role
	})
	if b.Policy.RegionWeights == nil {
		b.Policy.RegionWeights = map[string]int{}
	}
}
