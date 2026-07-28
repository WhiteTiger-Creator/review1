package output

import "fmt"

type Manifest struct {
	SchemaVersion string `json:"schema_version"`
	CampaignID    string `json:"campaign_id"`
	ModelRevision int    `json:"model_revision"`
	Generation    string `json:"generation"`
	Release       string `json:"release"`
	Provenance    string `json:"provenance"`
}

func Publish(root string, report Report, release, provenance []byte) error {
	_, _, _, _ = root, report, release, provenance
	return fmt.Errorf("atomic publication is not implemented")
}
