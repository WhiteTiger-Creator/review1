package load

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"

	"wakeclock/internal/model"
)

func Trace(path string) ([]model.TraceEvent, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	var events []model.TraceEvent
	last := 0
	line := 0
	for scanner.Scan() {
		line++
		data := bytes.TrimSpace(scanner.Bytes())
		if len(data) == 0 {
			continue
		}
		var event model.TraceEvent
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&event); err != nil {
			return nil, fmt.Errorf("trace line %d: %w", line, err)
		}
		if event.Seq <= last || (event.Kind != "boot" && event.Kind != "advance" && event.Kind != "set") || event.UTC == "" || (event.Kind == "boot" && event.BootID == "") {
			return nil, fmt.Errorf("invalid trace event")
		}
		last = event.Seq
		events = append(events, event)
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return events, nil
}
