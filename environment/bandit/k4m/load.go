package k4m

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Event is one logged bandit interaction.
type Event struct {
	EventID    string  `json:"event_id"`
	Timestamp  int64   `json:"timestamp"`
	ContextID  string  `json:"context_id"`
	Action     string  `json:"action"`
	Propensity float64 `json:"propensity"`
	Reward     float64 `json:"reward"`
}

// Bundle holds logs plus target policy and reward model tables.
type Bundle struct {
	Events       []Event
	Actions      []string
	Target       map[string]map[string]float64
	RewardModel  map[string]map[string]float64
	PolicyID     string
	RewardModelID string
}

type policyFile struct {
	PolicyID   string                        `json:"policy_id"`
	Actions    []string                      `json:"actions"`
	ByContext  map[string]map[string]float64 `json:"by_context"`
}

type rewardFile struct {
	ModelID   string                        `json:"model_id"`
	Actions   []string                      `json:"actions"`
	ByContext map[string]map[string]float64 `json:"by_context"`
}

// LoadExport reads interaction logs, action schema, target policy, and reward model.
func LoadExport(dataDir, featuresDir, modelsDir string) (Bundle, error) {
	logPath := filepath.Join(dataDir, "logs", "interactions.jsonl")
	events, err := readJSONL(logPath)
	if err != nil {
		return Bundle{}, err
	}

	polRaw, err := os.ReadFile(filepath.Join(modelsDir, "target_policy.json"))
	if err != nil {
		return Bundle{}, err
	}
	var pol policyFile
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return Bundle{}, err
	}

	rmRaw, err := os.ReadFile(filepath.Join(modelsDir, "reward_model.json"))
	if err != nil {
		return Bundle{}, err
	}
	var rm rewardFile
	if err := json.Unmarshal(rmRaw, &rm); err != nil {
		return Bundle{}, err
	}

	schemaPath := filepath.Join(featuresDir, "action_schema.json")
	if _, err := os.Stat(schemaPath); err != nil {
		return Bundle{}, fmt.Errorf("action schema: %w", err)
	}

	return Bundle{
		Events:        events,
		Actions:       pol.Actions,
		Target:        pol.ByContext,
		RewardModel:   rm.ByContext,
		PolicyID:      pol.PolicyID,
		RewardModelID: rm.ModelID,
	}, nil
}

func readJSONL(path string) ([]Event, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []Event
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for sc.Scan() {
		line := sc.Text()
		if line == "" {
			continue
		}
		var e Event
		if err := json.Unmarshal([]byte(line), &e); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, sc.Err()
}
