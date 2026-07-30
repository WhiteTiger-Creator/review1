package run

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"sort"
	"strings"

	"wavellite_dc/ingest"
	"wavellite_dc/q4"
)

func buildRow(bundle q4.Bundle) q4.SiteRow {
	units := append([]q4.Unit(nil), bundle.Units...)
	pol := bundle.Policy

	afterHosts, hostHeld := stageBa(units, pol)
	afterVolumes, volumeHeld := stageUv(afterHosts, pol)
	afterPaths, pathHeld := stagePr(afterVolumes, pol)
	afterSignoff, signoffHeld := stageDr(afterPaths, bundle.Approvals, pol)
	afterVisits, visitHeld := stageRc(afterSignoff, bundle.Maintenance, pol)
	afterZones, zoneHeld := stageZc(afterVisits, pol)
	kept, drawHeld := stageFd(afterZones, pol)

	row := q4.SiteRow{
		Name:              bundle.Name,
		RackCount:         len(units),
		CertifiedCount:    len(kept),
		ComputeBlocks:     hostHeld,
		StorageBlocks:     volumeHeld,
		NetworkBlocks:     pathHeld,
		ApprovalBlocks:    signoffHeld,
		MaintenanceBlocks: visitHeld,
		RegionRejections:  zoneHeld,
		CapacityTrims:     drawHeld,
	}
	return stageWm(row, kept, pol)
}

func programMark(rows []q4.SiteRow) string {
	marks := make([]string, len(rows))
	for i, row := range rows {
		marks[i] = row.Attestation
	}
	sort.Strings(marks)
	sum := sha256.Sum256([]byte(strings.Join(marks, "|")))
	return hex.EncodeToString(sum[:])
}

func RunAll() (q4.Report, error) {
	names, err := ingest.ListSites()
	if err != nil {
		return q4.Report{}, err
	}
	rows := make([]q4.SiteRow, 0, len(names))
	for _, name := range names {
		bundle, err := ingest.LoadBundle(name)
		if err != nil {
			return q4.Report{}, err
		}
		rows = append(rows, buildRow(bundle))
	}
	rep := q4.Report{SchemaVersion: 1, Sites: rows}
	rep.ProgramAttestation = programMark(rows)
	return rep, nil
}

func RunOne(name string) (q4.Report, error) {
	bundle, err := ingest.LoadBundle(name)
	if err != nil {
		return q4.Report{}, err
	}
	rows := []q4.SiteRow{buildRow(bundle)}
	rep := q4.Report{SchemaVersion: 1, Sites: rows}
	rep.ProgramAttestation = programMark(rows)
	return rep, nil
}

func WriteReport(path string, rep q4.Report) error {
	raw, err := json.MarshalIndent(rep, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o644)
}
