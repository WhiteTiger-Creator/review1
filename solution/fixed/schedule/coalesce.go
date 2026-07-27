package schedule

import (
	"sort"
	"time"

	"wakeclock/internal/model"
)

func Coalesce(ready []model.Occurrence) [][]model.Occurrence {
	items := append([]model.Occurrence{}, ready...)
	sort.Slice(items, func(i, j int) bool {
		if items[i].DelayedUTC != items[j].DelayedUTC {
			return items[i].DelayedUTC < items[j].DelayedUTC
		}
		if items[i].UnitID != items[j].UnitID {
			return items[i].UnitID < items[j].UnitID
		}
		return items[i].OccurrenceID < items[j].OccurrenceID
	})
	groups := [][]model.Occurrence{}
	var deadline time.Time
	for _, item := range items {
		when, _ := time.Parse(time.RFC3339, item.DelayedUTC)
		windowEnd := when.Add(time.Duration(item.AccuracySec) * time.Second)
		if len(groups) == 0 || when.After(deadline) {
			groups = append(groups, []model.Occurrence{item})
			deadline = windowEnd
			continue
		}
		groups[len(groups)-1] = append(groups[len(groups)-1], item)
		if windowEnd.Before(deadline) {
			deadline = windowEnd
		}
	}
	return groups
}
