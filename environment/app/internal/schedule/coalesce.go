package schedule

import (
	"sort"
	"time"

	"wakeclock/internal/model"
)

func Coalesce(ready []model.Occurrence) [][]model.Occurrence {
	items := append([]model.Occurrence{}, ready...)
	sort.Slice(items, func(i, j int) bool {
		if items[i].ScheduledUTC != items[j].ScheduledUTC {
			return items[i].ScheduledUTC < items[j].ScheduledUTC
		}
		return items[i].UnitID < items[j].UnitID
	})
	var groups [][]model.Occurrence
	for _, item := range items {
		when, _ := time.Parse(time.RFC3339, item.ScheduledUTC)
		if len(groups) == 0 {
			groups = append(groups, []model.Occurrence{item})
			continue
		}
		group := groups[len(groups)-1]
		anchor, _ := time.Parse(time.RFC3339, group[0].ScheduledUTC)
		if when.Sub(anchor) <= time.Duration(group[0].AccuracySec)*time.Second {
			groups[len(groups)-1] = append(group, item)
		} else {
			groups = append(groups, []model.Occurrence{item})
		}
	}
	return groups
}
