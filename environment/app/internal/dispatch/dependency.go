package dispatch

import (
	"sort"

	"wakeclock/internal/model"
)

func Order(group []model.Occurrence, state model.State) ([]model.Occurrence, []model.DependencyDecision, []model.Skipped) {
	items := append([]model.Occurrence{}, group...)
	sort.Slice(items, func(i, j int) bool {
		if items[i].Priority != items[j].Priority {
			return items[i].Priority > items[j].Priority
		}
		return items[i].UnitID < items[j].UnitID
	})
	decisions := make([]model.DependencyDecision, 0, len(items))
	for _, item := range items {
		decisions = append(decisions, model.DependencyDecision{UnitID: item.UnitID, OccurrenceID: item.OccurrenceID, Decision: "ready"})
	}
	return items, decisions, []model.Skipped{}
}
