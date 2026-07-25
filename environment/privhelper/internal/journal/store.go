package journal

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"

	"privhelper/internal/fsutil"
	"privhelper/internal/model"
)

// state is the persisted event-sequence counter.
type state struct {
	NextEventSeq int `json:"next_event_seq"`
}

// Trace optionally mirrors emitted events to a per-run trace file.
type Trace struct {
	Path string
}

// Store owns the journal file and the monotonic event-sequence counter kept in
// state.json.
type Store struct {
	Paths model.Paths
	Trace *Trace
}

// NewStore constructs a journal Store.
func NewStore(p model.Paths) *Store {
	return &Store{Paths: p}
}

func (s *Store) readState() state {
	b, err := os.ReadFile(s.Paths.State())
	if err != nil {
		return state{NextEventSeq: 1}
	}
	var st state
	if err := json.Unmarshal(b, &st); err != nil || st.NextEventSeq < 1 {
		return state{NextEventSeq: 1}
	}
	return st
}

func (s *Store) writeState(st state) error {
	b, err := json.Marshal(st)
	if err != nil {
		return err
	}
	return fsutil.AtomicWriteFile(s.Paths.State(), b, 0o644)
}

// InitState resets the counter to 1 (used by reset).
func (s *Store) InitState() error {
	return s.writeState(state{NextEventSeq: 1})
}

// PeekNextSeq returns the sequence that will be assigned to the next event.
func (s *Store) PeekNextSeq() int {
	return s.readState().NextEventSeq
}

// Emit assigns the next monotonic event_seq to ev, appends it durably to the
// journal (and the trace, if configured), and advances the persisted counter.
func (s *Store) Emit(ev *Event) error {
	st := s.readState()
	ev.EventSeq = st.NextEventSeq

	line, err := json.Marshal(ev)
	if err != nil {
		return err
	}
	if err := fsutil.AppendLineSync(s.Paths.Journal(), line); err != nil {
		return fmt.Errorf("append journal: %w", err)
	}
	if s.Trace != nil && s.Trace.Path != "" {
		if err := fsutil.AppendLineSync(s.Trace.Path, line); err != nil {
			return fmt.Errorf("append trace: %w", err)
		}
	}
	st.NextEventSeq++
	if err := s.writeState(st); err != nil {
		return fmt.Errorf("advance event seq: %w", err)
	}
	return nil
}

// LoadAll reads every journal event in file (sequence) order.
func (s *Store) LoadAll() ([]Event, error) {
	return LoadEvents(s.Paths.Journal())
}

// LoadEvents reads journal events from an arbitrary path.
func LoadEvents(path string) ([]Event, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var events []Event
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 8*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var ev Event
		if err := json.Unmarshal(line, &ev); err != nil {
			return nil, fmt.Errorf("parse journal line: %w", err)
		}
		events = append(events, ev)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return events, nil
}
