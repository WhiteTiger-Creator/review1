package recovery

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"wakeclock/internal/model"
)

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func removePending(state *model.State, ids []string) {
	set := map[string]bool{}
	for _, id := range ids {
		set[id] = true
	}
	kept := make([]model.Occurrence, 0, len(state.Pending))
	for _, item := range state.Pending {
		if set[item.OccurrenceID] {
			state.Cursors[item.UnitID] = item.OccurrenceID
			state.LastActivation[item.UnitID] = "recovered"
		} else {
			kept = append(kept, item)
		}
	}
	state.Pending = kept
}

func Apply(stateDir string, state *model.State, journal []model.JournalRecord) ([]model.RecoveryDecision, []model.JournalRecord, error) {
	byID := map[string][]model.JournalRecord{}
	for _, record := range journal {
		byID[record.ActivationID] = append(byID[record.ActivationID], record)
	}
	decisions := make([]model.RecoveryDecision, 0)
	for activationID, records := range byID {
		if contains(state.CommittedIDs, activationID) {
			continue
		}
		last := records[len(records)-1]
		if last.Phase == "prepare" {
			state.CommittedIDs = append(state.CommittedIDs, activationID)
			removePending(state, last.OccurrenceIDs)
			decisions = append(decisions, model.RecoveryDecision{ActivationID: activationID, Decision: "accepted_prepare"})
			continue
		}
		if last.Phase == "spool" {
			if _, err := os.Stat(filepath.Join(stateDir, "spool", activationID+".json")); err != nil {
				return nil, nil, fmt.Errorf("missing spool evidence")
			}
			journal = append(journal, model.JournalRecord{ActivationID: activationID, Phase: "commit", GroupID: last.GroupID, OccurrenceIDs: last.OccurrenceIDs})
			state.CommittedIDs = append(state.CommittedIDs, activationID)
			removePending(state, last.OccurrenceIDs)
			decisions = append(decisions, model.RecoveryDecision{ActivationID: activationID, Decision: "completed_spool"})
		}
		if last.Phase == "commit" {
			state.CommittedIDs = append(state.CommittedIDs, activationID)
			removePending(state, last.OccurrenceIDs)
			decisions = append(decisions, model.RecoveryDecision{ActivationID: activationID, Decision: "replayed_commit"})
		}
	}
	sort.Strings(state.CommittedIDs)
	sort.Slice(decisions, func(i, j int) bool { return decisions[i].ActivationID < decisions[j].ActivationID })
	return decisions, journal, nil
}
