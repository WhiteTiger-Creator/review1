package report

import (
	"encoding/json"
	"os"
	"path/filepath"

	"wakeclock/internal/model"
)

type SpoolWrite struct {
	ActivationID string
	Data         []byte
}

func encodeIndent(value any) ([]byte, error) {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(data, '\n'), nil
}

func WriteAll(stateDir, output string, state model.State, journal []model.JournalRecord, spools []SpoolWrite, report model.Report) error {
	stateData, err := encodeIndent(state)
	if err != nil {
		return err
	}
	reportData, err := encodeIndent(report)
	if err != nil {
		return err
	}
	journalData := make([]byte, 0)
	for _, record := range journal {
		line, err := json.Marshal(record)
		if err != nil {
			return err
		}
		journalData = append(journalData, line...)
		journalData = append(journalData, '\n')
	}
	if err := os.MkdirAll(filepath.Join(stateDir, "spool"), 0o755); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(output), 0o755); err != nil {
		return err
	}
	type staged struct{ temp, final string }
	var files []staged
	stage := func(final string, data []byte) error {
		file, err := os.CreateTemp(filepath.Dir(final), ".wakeclock-*.tmp")
		if err != nil {
			return err
		}
		name := file.Name()
		if _, err := file.Write(data); err != nil {
			file.Close()
			os.Remove(name)
			return err
		}
		if err := file.Sync(); err != nil {
			file.Close()
			os.Remove(name)
			return err
		}
		if err := file.Close(); err != nil {
			os.Remove(name)
			return err
		}
		files = append(files, staged{name, final})
		return nil
	}
	if err := stage(filepath.Join(stateDir, "snapshot.json"), stateData); err != nil {
		return err
	}
	if err := stage(filepath.Join(stateDir, "journal.jsonl"), journalData); err != nil {
		return err
	}
	for _, spool := range spools {
		if err := stage(filepath.Join(stateDir, "spool", spool.ActivationID+".json"), spool.Data); err != nil {
			return err
		}
	}
	if err := stage(output, reportData); err != nil {
		return err
	}
	for _, file := range files {
		if err := os.Rename(file.temp, file.final); err != nil {
			return err
		}
	}
	return nil
}
