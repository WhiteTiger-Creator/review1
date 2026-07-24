// Package ledger persists the authoritative decision and effect logs. Both are
// append-only and fsynced on every write so recovery and reconciliation can
// rebuild a faithful history after a crash.
package ledger

import (
	"bufio"
	"encoding/json"
	"os"

	"privhelper/internal/fsutil"
	"privhelper/internal/model"
)

// Decision is a single committed dispatcher decision.
type Decision struct {
	Seq                int    `json:"seq"`
	RequestID          string `json:"request_id"`
	RequestDigest      string `json:"request_digest"`
	Principal          string `json:"principal"`
	Action             string `json:"action"`
	Unit               string `json:"unit"`
	Decision           string `json:"decision"`
	Outcome            string `json:"outcome"`
	Reason             string `json:"reason"`
	HelperName         string `json:"helper_name"`
	HelperPath         string `json:"helper_path"`
	HelperDigest       string `json:"helper_digest"`
	ManifestGeneration int    `json:"manifest_generation"`
	ManifestDigest     string `json:"manifest_digest"`
	LaunchSurface      string `json:"launch_surface"`
}

// DecisionStore is the append-only decision log.
type DecisionStore struct {
	Paths model.Paths
}

// NewDecisionStore constructs a decision store.
func NewDecisionStore(p model.Paths) *DecisionStore {
	return &DecisionStore{Paths: p}
}

// Append durably writes one decision row.
func (s *DecisionStore) Append(d Decision) error {
	line, err := json.Marshal(d)
	if err != nil {
		return err
	}
	return fsutil.AppendLineSync(s.Paths.Decisions(), line)
}

// LoadAll reads every decision row in write order.
func (s *DecisionStore) LoadAll() ([]Decision, error) {
	f, err := os.Open(s.Paths.Decisions())
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var out []Decision
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 8*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var d Decision
		if err := json.Unmarshal(line, &d); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// FindByRequestID returns the most recent decision recorded for a request id,
// or false when none exists.
func (s *DecisionStore) FindByRequestID(requestID string) (Decision, bool, error) {
	all, err := s.LoadAll()
	if err != nil {
		return Decision{}, false, err
	}
	var found Decision
	ok := false
	for _, d := range all {
		if d.RequestID == requestID {
			found = d
			ok = true
		}
	}
	return found, ok, nil
}
