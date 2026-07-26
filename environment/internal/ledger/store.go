package ledger

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type Entry struct {
	CampaignID   string `json:"campaign_id"`
	BundleDigest string `json:"bundle_digest"`
	Epoch        int    `json:"epoch"`
	Status       string `json:"status"`
}

func Append(varDir string, e Entry) error {
	if err := os.MkdirAll(varDir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(varDir, "chironym_ledger.json")
	var rows []Entry
	if b, err := os.ReadFile(path); err == nil && len(b) > 0 {
		_ = json.Unmarshal(b, &rows)
	}
	rows = append(rows, e)
	out, err := json.MarshalIndent(rows, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, out, 0o644)
}
