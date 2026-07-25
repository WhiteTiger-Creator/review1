package ledger

import (
	"bufio"
	"encoding/json"
	"os"

	"privhelper/internal/fsutil"
	"privhelper/internal/model"
)

// Effect is a single applied privileged effect.
type Effect struct {
	Seq                int    `json:"seq"`
	RequestID          string `json:"request_id"`
	RequestDigest      string `json:"request_digest"`
	Principal          string `json:"principal"`
	Action             string `json:"action"`
	Unit               string `json:"unit"`
	Effect             string `json:"effect"`
	HelperName         string `json:"helper_name"`
	HelperPath         string `json:"helper_path"`
	HelperDigest       string `json:"helper_digest"`
	ManifestGeneration int    `json:"manifest_generation"`
	ManifestDigest     string `json:"manifest_digest"`
}

// EffectStore is the append-only effect log.
type EffectStore struct {
	Paths model.Paths
}

// NewEffectStore constructs an effect store.
func NewEffectStore(p model.Paths) *EffectStore {
	return &EffectStore{Paths: p}
}

// Append durably writes one effect row.
func (s *EffectStore) Append(e Effect) error {
	line, err := json.Marshal(e)
	if err != nil {
		return err
	}
	return fsutil.AppendLineSync(s.Paths.Effects(), line)
}

// LoadAll reads every effect row in write order.
func (s *EffectStore) LoadAll() ([]Effect, error) {
	f, err := os.Open(s.Paths.Effects())
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var out []Effect
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 8*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var e Effect
		if err := json.Unmarshal(line, &e); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// FindByRequestID returns effects recorded for a request id.
func (s *EffectStore) FindByRequestID(requestID string) ([]Effect, error) {
	all, err := s.LoadAll()
	if err != nil {
		return nil, err
	}
	var out []Effect
	for _, e := range all {
		if e.RequestID == requestID {
			out = append(out, e)
		}
	}
	return out, nil
}
