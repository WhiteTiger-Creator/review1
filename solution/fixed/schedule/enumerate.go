package schedule

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"sort"
	"time"

	_ "time/tzdata"

	"wakeclock/internal/model"
)

func weekdayAllowed(days []int, day time.Weekday) bool {
	for _, value := range days {
		if value == int(day) {
			return true
		}
	}
	return false
}

func Enumerate(units []model.Unit, start, end time.Time, eventTime time.Time) ([]model.Occurrence, error) {
	locations := map[string]*time.Location{}
	for _, unit := range units {
		location, err := time.LoadLocation(unit.Timezone)
		if err != nil {
			return nil, err
		}
		locations[unit.UnitID] = location
	}
	result := []model.Occurrence{}
	startMinute := start.UTC().Truncate(time.Minute).Add(time.Minute)
	for instant := startMinute; !instant.After(end); instant = instant.Add(time.Minute) {
		for _, unit := range units {
			if !unit.Enabled {
				continue
			}
			local := instant.In(locations[unit.UnitID])
			if local.Hour() != unit.Hour || local.Minute() != unit.Minute || !weekdayAllowed(unit.Weekdays, local.Weekday()) {
				continue
			}
			if !unit.Persistent && !instant.Equal(eventTime) {
				continue
			}
			_, offset := local.Zone()
			localText := local.Format("2006-01-02T15:04:05")
			utcText := instant.UTC().Format(time.RFC3339)
			occurrenceID := fmt.Sprintf("%s|%s|%d|%s", unit.UnitID, localText, offset, utcText)
			seed := sha256.Sum256([]byte(unit.UnitID + "\n" + occurrenceID + "\n" + unit.Salt + "\n"))
			delay := binary.BigEndian.Uint64(seed[:8]) % uint64(unit.RandomDelaySec+1)
			result = append(result, model.Occurrence{
				UnitID:         unit.UnitID,
				OccurrenceID:   occurrenceID,
				ScheduledLocal: localText,
				ScheduledUTC:   utcText,
				OffsetSec:      offset,
				DelayedUTC:     instant.Add(time.Duration(delay) * time.Second).UTC().Format(time.RFC3339),
				AccuracySec:    unit.AccuracySec,
				Priority:       unit.Priority,
				DependsOn:      append([]string{}, unit.DependsOn...),
			})
		}
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].ScheduledUTC != result[j].ScheduledUTC {
			return result[i].ScheduledUTC < result[j].ScheduledUTC
		}
		if result[i].UnitID != result[j].UnitID {
			return result[i].UnitID < result[j].UnitID
		}
		return result[i].OccurrenceID < result[j].OccurrenceID
	})
	return result, nil
}
