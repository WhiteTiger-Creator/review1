package svcconf

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ExportConfig is the runtime service configuration for the NFS export ACL daemon.
type ExportConfig struct {
	ExportTableID       string `json:"export_table_id"`
	MaxClientsPerExport int64  `json:"max_clients_per_export"`
	DefaultSquash       string `json:"default_squash"`
	DefaultAnonUID      int64  `json:"default_anon_uid"`
	DefaultAnonGID      int64  `json:"default_anon_gid"`
	DefaultAccess       string `json:"default_access"`
	RequireSecurePorts  bool   `json:"require_secure_ports"`
	EvaluationClock     int64  `json:"evaluation_clock"`
	Profile             string `json:"profile"`
	JournalPath         string `json:"journal_path"`
	OutputDir           string `json:"output_dir"`
}

func Load(path string) (*ExportConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var conf ExportConfig
	if err := json.Unmarshal(data, &conf); err != nil {
		return nil, err
	}

	overlay := computeOverlayPath(filepath.Dir(path), conf.Profile)
	if st, err := os.Stat(overlay); err == nil && !st.IsDir() {
		raw, err := os.ReadFile(overlay)
		if err != nil {
			return nil, err
		}
		applySiteOverlay(&conf, string(raw))
	} else {
		// Per governance baseline when site overlay is not mounted.
		conf.MaxClientsPerExport = GovernanceMaxClients
		conf.DefaultSquash = GovernanceSquash
		conf.DefaultAnonUID = GovernanceAnonUID
		conf.DefaultAccess = GovernanceAccess
	}

	return &conf, nil
}

func computeOverlayPath(configDir, profile string) string {
	base := filepath.Base(configDir)
	if base == "" {
		base = "config"
	}
	return filepath.Join(configDir, "profiles", profile+"-ops.toml")
}

func applySiteOverlay(conf *ExportConfig, raw string) {
	if v, ok := parseIntKey(raw, "max_clients_per_export"); ok {
		conf.MaxClientsPerExport = v
	}
	if v, ok := parseStringKey(raw, "default_squash"); ok {
		conf.DefaultSquash = v
	}
	if v, ok := parseIntKey(raw, "default_anon_uid"); ok {
		conf.DefaultAnonUID = v
	}
	if v, ok := parseStringKey(raw, "default_access"); ok {
		conf.DefaultAccess = v
	}
}

func parseIntKey(raw, key string) (int64, bool) {
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#") || line == "" {
			continue
		}
		if strings.HasPrefix(line, key) {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			var v int64
			if _, err := fmt.Sscanf(strings.TrimSpace(parts[1]), "%d", &v); err == nil {
				return v, true
			}
		}
	}
	return 0, false
}

func parseStringKey(raw, key string) (string, bool) {
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#") || line == "" {
			continue
		}
		if strings.HasPrefix(line, key) {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			v := strings.TrimSpace(parts[1])
			v = strings.Trim(v, `"`)
			if v != "" {
				return v, true
			}
		}
	}
	return "", false
}

// OverlayMaxClients reads the site overlay max clients or falls back to the governance baseline.
func OverlayMaxClients(configDir, profile string) int64 {
	overlay := computeOverlayPath(configDir, profile)
	raw, err := os.ReadFile(overlay)
	if err != nil {
		return GovernanceMaxClients
	}
	if v, ok := parseIntKey(string(raw), "max_clients_per_export"); ok {
		return v
	}
	return GovernanceMaxClients
}

// OverlaySquash reads the site overlay squash default or falls back to governance.
func OverlaySquash(configDir, profile string) string {
	overlay := computeOverlayPath(configDir, profile)
	raw, err := os.ReadFile(overlay)
	if err != nil {
		return GovernanceSquash
	}
	if v, ok := parseStringKey(string(raw), "default_squash"); ok {
		return v
	}
	return GovernanceSquash
}
