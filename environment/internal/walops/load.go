package walops

import (
	"bufio"
	"encoding/json"
	"os"
)

// Op is one journaled NFS export ACL operation.
type Op struct {
	OpID       string  `json:"op_id"`
	Ts         int64   `json:"ts"`
	Type       string  `json:"type"`
	ExportPath string  `json:"export_path"`
	ClientID   string  `json:"client_id"`
	Access     *string `json:"access"`
	Squash     *string `json:"squash"`
	AnonUID    *int64  `json:"anon_uid"`
	AnonGID    *int64  `json:"anon_gid"`
	Secure     *bool   `json:"secure"`
}

func Load(path string) ([]Op, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var ops []Op
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if line == "" {
			continue
		}
		var op Op
		if err := json.Unmarshal([]byte(line), &op); err != nil {
			return nil, err
		}
		ops = append(ops, op)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return ops, nil
}
