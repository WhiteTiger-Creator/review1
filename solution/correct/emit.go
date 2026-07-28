package runtime

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"

	"nfsacld/internal/exportacl"
)

func roundHalfAway(value float64, ndigits int) float64 {
	factor := math.Pow(10, float64(ndigits))
	scaled := value * factor
	if scaled >= 0 {
		return math.Floor(scaled+0.5) / factor
	}
	return math.Ceil(scaled-0.5) / factor
}

// Emit persists export ACL inventory and compliance metrics.
func Emit(
	outputDir string,
	tableID string,
	evalClock int64,
	maxClients int64,
	exports []exportacl.Export,
	wait []exportacl.WaitEntry,
	applied, skipped int64,
) error {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return err
	}

	type aclDoc struct {
		EvaluationClock     int64                `json:"evaluation_clock"`
		ExportTableID       string               `json:"export_table_id"`
		MaxClientsPerExport int64                `json:"max_clients_per_export"`
		Exports             []exportacl.Export   `json:"exports"`
		Waitlist            []exportacl.WaitEntry `json:"waitlist"`
	}
	acl := aclDoc{
		EvaluationClock:     evalClock,
		ExportTableID:       tableID,
		MaxClientsPerExport: maxClients,
		Exports:             exports,
		Waitlist:            wait,
	}
	if acl.Waitlist == nil {
		acl.Waitlist = []exportacl.WaitEntry{}
	}
	for i := range acl.Exports {
		if acl.Exports[i].Clients == nil {
			acl.Exports[i].Clients = []*exportacl.ClientGrant{}
		}
	}

	aclBytes, err := json.MarshalIndent(acl, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(outputDir, "export_acls.json"), aclBytes, 0o644); err != nil {
		return err
	}

	var grantCount, insecure, overCap int64
	for _, exp := range exports {
		n := int64(len(exp.Clients))
		grantCount += n
		if n > maxClients {
			overCap++
		}
		for _, c := range exp.Clients {
			if c.State == "insecure" {
				insecure++
			}
		}
	}
	exportCount := int64(len(exports))
	waitDepth := int64(len(wait))

	util := 0.0
	if exportCount > 0 {
		util = roundHalfAway(float64(grantCount)/float64(exportCount*maxClients), 4)
	}
	penalties := float64(insecure)*20 + float64(overCap)*25 + float64(waitDepth)*2
	compliance := math.Max(0, roundHalfAway(100-penalties, 2))

	metrics := map[string]any{
		"export_count":            exportCount,
		"client_grant_count":      grantCount,
		"waitlist_depth":          waitDepth,
		"insecure_grant_count":    insecure,
		"over_capacity_exports":   overCap,
		"journal_applied":         applied,
		"journal_skipped_dup":     skipped,
		"slot_utilization_ratio":  util,
		"export_compliance":       compliance,
	}
	mBytes, err := json.MarshalIndent(metrics, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(outputDir, "export_metrics.json"), mBytes, 0o644)
}
