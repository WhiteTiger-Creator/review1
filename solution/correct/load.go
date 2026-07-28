package svcconf

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// ExportConfig is the runtime service configuration for the NFS export ACL daemon.
type ExportConfig struct {
	ExportTableID         string `json:"export_table_id"`
	MaxClientsPerExport   int64  `json:"max_clients_per_export"`
	DefaultSquash         string `json:"default_squash"`
	DefaultAnonUID        int64  `json:"default_anon_uid"`
	DefaultAnonGID        int64  `json:"default_anon_gid"`
	DefaultAccess         string `json:"default_access"`
	RequireSecurePorts    bool   `json:"require_secure_ports"`
	EvaluationClock       int64  `json:"evaluation_clock"`
	Profile               string `json:"profile"`
	JournalPath           string `json:"journal_path"`
	OutputDir             string `json:"output_dir"`
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

	// Base exports.json max_clients_per_export and defaults are authoritative.
	// Profile overlays must not alter max clients, squash/access/anon defaults,
	// secure-port enforcement, table id, or evaluation clock.
	_ = computeOverlayPath(filepath.Dir(path), conf.Profile)

	return &conf, nil
}

func computeOverlayPath(configDir, profile string) string {
	return filepath.Join(configDir, "profiles", profile+"-ops.toml")
}

// OverlayMaxClients is retained for callers that discover overlays; base config remains authoritative.
func OverlayMaxClients(configDir, profile string) int64 {
	_ = computeOverlayPath(configDir, profile)
	return 0
}

// OverlaySquash is retained for API compatibility with regional tooling.
func OverlaySquash(configDir, profile string) string {
	_ = computeOverlayPath(configDir, profile)
	return ""
}
