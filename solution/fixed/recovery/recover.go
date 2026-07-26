package recovery

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"wakeclock/internal/model"
)

type activationEvidence struct {
	records    []model.JournalRecord
	activation model.Activation
	hasSpool   bool
	hasCommit  bool
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func sameStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func removePending(state *model.State, ids []string, activation model.Activation) {
	set := map[string]bool{}
	for _, id := range ids {
		set[id] = true
	}
	kept := make([]model.Occurrence, 0, len(state.Pending))
	for _, item := range state.Pending {
		if set[item.OccurrenceID] {
			state.Cursors[item.UnitID] = item.OccurrenceID
		} else {
			kept = append(kept, item)
		}
	}
	state.Pending = kept
	for _, unitID := range activation.UnitIDs {
		state.LastActivation[unitID] = activation.ActivationID
	}
}

func readSpool(path string, expected model.JournalRecord) (model.Activation, error) {
	var activation model.Activation
	data, err := os.ReadFile(path)
	if err != nil {
		return activation, fmt.Errorf("missing spool evidence")
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&activation); err != nil {
		return activation, fmt.Errorf("invalid spool evidence")
	}
	if activation.ActivationID != expected.ActivationID || activation.GroupID != expected.GroupID || len(activation.OccurrenceIDs) == 0 {
		return activation, fmt.Errorf("inconsistent spool evidence")
	}
	allowed := map[string]bool{}
	for _, id := range expected.OccurrenceIDs {
		allowed[id] = true
	}
	for _, id := range activation.OccurrenceIDs {
		if !allowed[id] {
			return activation, fmt.Errorf("inconsistent spool evidence")
		}
	}
	return activation, nil
}

func Apply(stateDir string, state *model.State, journal []model.JournalRecord) ([]model.RecoveryDecision, []model.JournalRecord, error) {
	byID := map[string][]model.JournalRecord{}
	order := []string{}
	for _, record := range journal {
		if len(byID[record.ActivationID]) == 0 {
			order = append(order, record.ActivationID)
		}
		byID[record.ActivationID] = append(byID[record.ActivationID], record)
	}

	evidence := map[string]activationEvidence{}
	for activationID, records := range byID {
		if records[0].Phase != "prepare" || len(records) > 3 {
			return nil, nil, fmt.Errorf("invalid journal phase order")
		}
		base := records[0]
		phases := []string{"prepare", "spool", "commit"}
		for index, record := range records {
			if record.Phase != phases[index] || record.GroupID != base.GroupID || !sameStrings(record.OccurrenceIDs, base.OccurrenceIDs) {
				return nil, nil, fmt.Errorf("inconsistent journal evidence")
			}
		}
		item := activationEvidence{records: records, hasSpool: len(records) >= 2, hasCommit: len(records) == 3}
		spoolPath := filepath.Join(stateDir, "spool", activationID+".json")
		if item.hasSpool {
			activation, err := readSpool(spoolPath, base)
			if err != nil {
				return nil, nil, err
			}
			item.activation = activation
		} else if _, err := os.Stat(spoolPath); err == nil {
			return nil, nil, fmt.Errorf("unexpected spool evidence")
		} else if !os.IsNotExist(err) {
			return nil, nil, err
		}
		evidence[activationID] = item
	}

	entries, err := os.ReadDir(filepath.Join(stateDir, "spool"))
	if err != nil {
		if os.IsNotExist(err) {
			entries = nil
		} else {
			return nil, nil, err
		}
	}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			return nil, nil, fmt.Errorf("unexpected spool evidence")
		}
		activationID := entry.Name()[:len(entry.Name())-len(".json")]
		if !evidence[activationID].hasSpool {
			return nil, nil, fmt.Errorf("unexpected spool evidence")
		}
	}
	for _, activationID := range state.CommittedIDs {
		if !evidence[activationID].hasCommit {
			return nil, nil, fmt.Errorf("committed activation lacks journal evidence")
		}
	}

	decisions := []model.RecoveryDecision{}
	keptJournal := make([]model.JournalRecord, 0, len(journal)+len(order))
	for _, activationID := range order {
		item := evidence[activationID]
		base := item.records[0]
		if !item.hasSpool {
			decisions = append(decisions, model.RecoveryDecision{ActivationID: activationID, Decision: "discarded_prepare"})
			continue
		}
		keptJournal = append(keptJournal, item.records...)
		if item.hasCommit {
			if !contains(state.CommittedIDs, activationID) {
				state.CommittedIDs = append(state.CommittedIDs, activationID)
				removePending(state, base.OccurrenceIDs, item.activation)
				decisions = append(decisions, model.RecoveryDecision{ActivationID: activationID, Decision: "replayed_commit"})
			}
			continue
		}
		commit := model.JournalRecord{ActivationID: activationID, Phase: "commit", GroupID: base.GroupID, OccurrenceIDs: append([]string{}, base.OccurrenceIDs...)}
		keptJournal = append(keptJournal, commit)
		state.CommittedIDs = append(state.CommittedIDs, activationID)
		removePending(state, base.OccurrenceIDs, item.activation)
		decisions = append(decisions, model.RecoveryDecision{ActivationID: activationID, Decision: "completed_spool"})
	}
	sort.Strings(state.CommittedIDs)
	sort.Slice(decisions, func(i, j int) bool { return decisions[i].ActivationID < decisions[j].ActivationID })
	return decisions, keptJournal, nil
}
