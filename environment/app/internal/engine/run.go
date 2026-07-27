package engine

import (
	"encoding/json"
	"fmt"
	"sort"
	"time"

	"wakeclock/internal/digest"
	"wakeclock/internal/dispatch"
	"wakeclock/internal/load"
	"wakeclock/internal/model"
	"wakeclock/internal/recovery"
	"wakeclock/internal/report"
	"wakeclock/internal/schedule"
)

func Run(args []string) error {
	options, err := parse(args)
	if err != nil {
		return err
	}
	units, err := load.Units(options.units)
	if err != nil {
		return err
	}
	state, journal, err := load.State(options.state)
	if err != nil {
		return err
	}
	events, err := load.Trace(options.clock)
	if err != nil {
		return err
	}
	if err := validateStateTimes(state); err != nil {
		return err
	}

	recovered, journal, err := recovery.Apply(options.state, &state, journal)
	if err != nil {
		return err
	}
	result := model.Report{
		SchemaVersion:       "wakeclock.reconcile.v1",
		TraceSeq:            state.TraceSeq,
		Recovered:           recovered,
		Activations:         []model.Activation{},
		Skipped:             []model.Skipped{},
		CoalescingGroups:    []model.CoalescingGroup{},
		DependencyDecisions: []model.DependencyDecision{},
		FinalCursors:        map[string]string{},
	}
	spools := []report.SpoolWrite{}
	committed := stringSet(state.CommittedIDs)
	seen := occurrenceSet(state.Pending)

	for _, event := range events {
		if event.Seq <= state.TraceSeq {
			continue
		}
		instant, err := time.Parse(time.RFC3339, event.UTC)
		if err != nil {
			return fmt.Errorf("invalid trace time")
		}
		instant = instant.UTC()
		highWater, _ := time.Parse(time.RFC3339, state.HighWaterUTC)
		if instant.After(highWater) {
			occurrences, err := schedule.Enumerate(units, highWater.UTC(), instant, instant)
			if err != nil {
				return err
			}
			for _, occurrence := range occurrences {
				if !seen[occurrence.OccurrenceID] && !committed[occurrence.OccurrenceID] {
					state.Pending = append(state.Pending, occurrence)
					seen[occurrence.OccurrenceID] = true
				}
			}
			state.HighWaterUTC = instant.Format(time.RFC3339)
		}
		state.ClockUTC = instant.Format(time.RFC3339)
		state.TraceSeq = event.Seq
		if event.Kind == "boot" {
			state.BootID = event.BootID
		}
		applyCatchUpCaps(units, &state, &result, seen)
		if err := dispatchReady(&state, &journal, &spools, &result); err != nil {
			return err
		}
		result.TraceSeq = state.TraceSeq
	}

	sortState(&state)
	stateDigest, err := digest.State(state)
	if err != nil {
		return err
	}
	for key, value := range state.Cursors {
		result.FinalCursors[key] = value
	}
	result.StateDigest = stateDigest
	return report.WriteAll(options.state, options.output, state, journal, spools, result)
}

func validateStateTimes(state model.State) error {
	clock, err := time.Parse(time.RFC3339, state.ClockUTC)
	if err != nil {
		return fmt.Errorf("invalid state clock")
	}
	highWater, err := time.Parse(time.RFC3339, state.HighWaterUTC)
	if err != nil || highWater.Before(clock) {
		return fmt.Errorf("invalid state high-water mark")
	}
	for _, occurrence := range state.Pending {
		if occurrence.UnitID == "" || occurrence.OccurrenceID == "" {
			return fmt.Errorf("invalid pending occurrence")
		}
		if _, err := time.Parse(time.RFC3339, occurrence.ScheduledUTC); err != nil {
			return fmt.Errorf("invalid pending occurrence")
		}
		if _, err := time.Parse(time.RFC3339, occurrence.DelayedUTC); err != nil {
			return fmt.Errorf("invalid pending occurrence")
		}
	}
	return nil
}

func dispatchReady(state *model.State, journal *[]model.JournalRecord, spools *[]report.SpoolWrite, result *model.Report) error {
	clock, _ := time.Parse(time.RFC3339, state.ClockUTC)
	ready := []model.Occurrence{}
	for _, occurrence := range state.Pending {
		delayed, _ := time.Parse(time.RFC3339, occurrence.DelayedUTC)
		if !delayed.After(clock) {
			ready = append(ready, occurrence)
		}
	}
	for _, group := range schedule.Coalesce(ready) {
		groupID, activationID, effectiveUTC, allIDs := dispatch.IDs(group)
		result.CoalescingGroups = append(result.CoalescingGroups, model.CoalescingGroup{
			GroupID:       groupID,
			EffectiveUTC:  effectiveUTC,
			OccurrenceIDs: allIDs,
		})
		ordered, decisions, skipped := dispatch.Order(group, *state)
		result.DependencyDecisions = append(result.DependencyDecisions, decisions...)
		result.Skipped = append(result.Skipped, skipped...)
		for _, item := range skipped {
			consumeOccurrence(state, item.UnitID, item.OccurrenceID, "")
		}
		if len(ordered) == 0 {
			continue
		}
		unitIDs := make([]string, 0, len(ordered))
		occurrenceIDs := make([]string, 0, len(ordered))
		for _, item := range ordered {
			unitIDs = append(unitIDs, item.UnitID)
			occurrenceIDs = append(occurrenceIDs, item.OccurrenceID)
		}
		activation := model.Activation{
			ActivationID:  activationID,
			GroupID:       groupID,
			EffectiveUTC:  effectiveUTC,
			UnitIDs:       unitIDs,
			OccurrenceIDs: occurrenceIDs,
		}
		spoolData, err := json.MarshalIndent(activation, "", "  ")
		if err != nil {
			return err
		}
		spoolData = append(spoolData, '\n')
		*journal = append(*journal,
			model.JournalRecord{ActivationID: activationID, Phase: "prepare", GroupID: groupID, OccurrenceIDs: allIDs},
			model.JournalRecord{ActivationID: activationID, Phase: "spool", GroupID: groupID, OccurrenceIDs: allIDs},
			model.JournalRecord{ActivationID: activationID, Phase: "commit", GroupID: groupID, OccurrenceIDs: allIDs},
		)
		*spools = append(*spools, report.SpoolWrite{ActivationID: activationID, Data: spoolData})
		state.CommittedIDs = append(state.CommittedIDs, activationID)
		for _, item := range ordered {
			consumeOccurrence(state, item.UnitID, item.OccurrenceID, activationID)
		}
		result.Activations = append(result.Activations, activation)
	}
	return nil
}

func consumeOccurrence(state *model.State, unitID, occurrenceID, activationID string) {
	kept := make([]model.Occurrence, 0, len(state.Pending))
	for _, item := range state.Pending {
		if item.OccurrenceID != occurrenceID {
			kept = append(kept, item)
		}
	}
	state.Pending = kept
	state.Cursors[unitID] = occurrenceID
	if activationID != "" {
		state.LastActivation[unitID] = activationID
	}
}

func applyCatchUpCaps(units []model.Unit, state *model.State, result *model.Report, seen map[string]bool) {
	caps := map[string]int{}
	for _, unit := range units {
		caps[unit.UnitID] = unit.CatchUpCap
	}
	byUnit := map[string][]model.Occurrence{}
	for _, item := range state.Pending {
		byUnit[item.UnitID] = append(byUnit[item.UnitID], item)
	}
	drop := map[string]bool{}
	unitIDs := make([]string, 0, len(byUnit))
	for unitID := range byUnit {
		unitIDs = append(unitIDs, unitID)
	}
	sort.Strings(unitIDs)
	for _, unitID := range unitIDs {
		items := byUnit[unitID]
		sort.Slice(items, func(i, j int) bool {
			if items[i].ScheduledUTC != items[j].ScheduledUTC {
				return items[i].ScheduledUTC < items[j].ScheduledUTC
			}
			return items[i].OccurrenceID < items[j].OccurrenceID
		})
		cap := caps[unitID]
		for len(items) > cap {
			item := items[0]
			items = items[1:]
			drop[item.OccurrenceID] = true
			delete(seen, item.OccurrenceID)
			state.Cursors[item.UnitID] = item.OccurrenceID
			result.Skipped = append(result.Skipped, model.Skipped{OccurrenceID: item.OccurrenceID, UnitID: item.UnitID, Reason: "catch_up_cap"})
			result.DependencyDecisions = append(result.DependencyDecisions, model.DependencyDecision{UnitID: item.UnitID, OccurrenceID: item.OccurrenceID, Decision: "skipped_catch_up_cap"})
		}
	}
	kept := make([]model.Occurrence, 0, len(state.Pending))
	for _, item := range state.Pending {
		if !drop[item.OccurrenceID] {
			kept = append(kept, item)
		}
	}
	state.Pending = kept
}

func sortState(state *model.State) {
	sort.Slice(state.Pending, func(i, j int) bool {
		if state.Pending[i].DelayedUTC != state.Pending[j].DelayedUTC {
			return state.Pending[i].DelayedUTC < state.Pending[j].DelayedUTC
		}
		if state.Pending[i].UnitID != state.Pending[j].UnitID {
			return state.Pending[i].UnitID < state.Pending[j].UnitID
		}
		return state.Pending[i].OccurrenceID < state.Pending[j].OccurrenceID
	})
	sort.Strings(state.CommittedIDs)
	state.CommittedIDs = uniqueStrings(state.CommittedIDs)
}

func uniqueStrings(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if len(result) == 0 || result[len(result)-1] != value {
			result = append(result, value)
		}
	}
	return result
}

func stringSet(values []string) map[string]bool {
	result := map[string]bool{}
	for _, value := range values {
		result[value] = true
	}
	return result
}

func occurrenceSet(values []model.Occurrence) map[string]bool {
	result := map[string]bool{}
	for _, value := range values {
		result[value.OccurrenceID] = true
	}
	return result
}
