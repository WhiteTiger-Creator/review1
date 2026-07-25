// Package report defines the authority reconciliation report and the
// deterministic ledger digest used to seal it.
package report

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"sort"

	"privhelper/internal/model"
)

// Report is the exact schema written by `reconcile --output`.
type Report struct {
	Scenario           string   `json:"scenario"`
	ManifestGeneration int      `json:"manifest_generation"`
	ManifestDigest     string   `json:"manifest_digest"`
	AuthoritySound     bool     `json:"authority_sound"`
	Violations         []string `json:"violations"`
	RequestsSeen       int      `json:"requests_seen"`
	CommittedRequests  int      `json:"committed_requests"`
	DeniedRequests     int      `json:"denied_requests"`
	PendingRequests    int      `json:"pending_requests"`
	ConflictRequests   int      `json:"conflict_requests"`
	EffectsApplied     int      `json:"effects_applied"`
	HelpersTrusted     bool     `json:"helpers_trusted"`
	RecoveryComplete   bool     `json:"recovery_complete"`
	IdempotencySound   bool     `json:"idempotency_sound"`
	Journal            string   `json:"journal"`
	DecisionLog        string   `json:"decision_log"`
	EffectLog          string   `json:"effect_log"`
	Manifest           string   `json:"manifest"`
	Trace              string   `json:"trace"`
	LedgerDigest       string   `json:"ledger_digest"`
}

// Write marshals the report as indented JSON and writes it to path.
func Write(path string, r Report) error {
	if r.Violations == nil {
		r.Violations = []string{}
	}
	b, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

// ComputeLedgerDigest builds the canonical, sorted-key JSON document
// {"decisions":[...],"effects":[...],"journal":[...]} with each array ordered
// by seq/event_seq, and returns its SHA-256 hex digest.
func ComputeLedgerDigest(p model.Paths) (string, error) {
	decisions, err := loadSortedRecords(p.Decisions(), "seq")
	if err != nil {
		return "", err
	}
	effects, err := loadSortedRecords(p.Effects(), "seq")
	if err != nil {
		return "", err
	}
	journal, err := loadSortedRecords(p.Journal(), "event_seq")
	if err != nil {
		return "", err
	}

	payload := map[string]any{
		"decisions": decisions,
		"effects":   effects,
		"journal":   journal,
	}
	// encoding/json marshals map keys in sorted order and uses compact
	// separators, which yields a deterministic pre-image.
	b, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:]), nil
}

func loadSortedRecords(path, seqKey string) ([]map[string]any, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []map[string]any{}, nil
		}
		return nil, err
	}
	defer f.Close()

	var records []map[string]any
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 8*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal(line, &m); err != nil {
			return nil, err
		}
		records = append(records, m)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	sort.SliceStable(records, func(i, j int) bool {
		return seqOf(records[i], seqKey) < seqOf(records[j], seqKey)
	})
	if records == nil {
		records = []map[string]any{}
	}
	return records, nil
}

func seqOf(m map[string]any, key string) float64 {
	if v, ok := m[key]; ok {
		if f, ok := v.(float64); ok {
			return f
		}
	}
	return 0
}
