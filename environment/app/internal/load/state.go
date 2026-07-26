package load

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"wakeclock/internal/model"
)

func State(dir string) (model.State, []model.JournalRecord, error) {
	var state model.State
	if err := Object(filepath.Join(dir, "snapshot.json"), &state); err != nil {
		return state, nil, err
	}
	if state.SchemaVersion != "wakeclock.state.v1" || state.LastActivation == nil || state.Cursors == nil {
		return state, nil, fmt.Errorf("invalid state")
	}
	file, err := os.Open(filepath.Join(dir, "journal.jsonl"))
	if err != nil {
		return state, nil, err
	}
	defer file.Close()
	var journal []model.JournalRecord
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		data := bytes.TrimSpace(scanner.Bytes())
		if len(data) == 0 {
			continue
		}
		var record model.JournalRecord
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&record); err != nil {
			return state, nil, err
		}
		if record.ActivationID == "" || record.GroupID == "" || len(record.OccurrenceIDs) == 0 || (record.Phase != "prepare" && record.Phase != "spool" && record.Phase != "commit") {
			return state, nil, fmt.Errorf("invalid journal")
		}
		journal = append(journal, record)
	}
	if err := scanner.Err(); err != nil {
		return state, nil, err
	}
	sort.Strings(state.CommittedIDs)
	return state, journal, nil
}
