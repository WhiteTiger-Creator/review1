package store

import (
	"encoding/json"
	"os"
	"path/filepath"
)

func haul_u(ledger *SegmentLedger, outDir string) error {
	prevPath := filepath.Join(outDir, "push_trace.json")
	b, err := os.ReadFile(prevPath)
	if err != nil {
		return nil
	}
	var prev PushTrace
	if json.Unmarshal(b, &prev) != nil {
		return nil
	}
	var anchor int
	for _, row := range prev.Segments {
		if row.LegID == "leg-a" {
			anchor = row.ByteOffset
		}
	}
	for _, row := range prev.Segments {
		r := row
		if r.LegID == "leg-b" {
			r.ByteOffset = anchor
		}
		ledger.Append(r)
	}
	return nil
}

func HaulRows(ledger *SegmentLedger, outDir string, appendMode bool) error {
	if !appendMode {
		return nil
	}
	return haul_u(ledger, outDir)
}

func resume_gate(outDir string, cycle int) bool {
	convPath := filepath.Join(outDir, "convergence_report.json")
	b, err := os.ReadFile(convPath)
	if err != nil {
		return false
	}
	var existing ConvReport
	if json.Unmarshal(b, &existing) != nil {
		return false
	}
	for _, c := range existing.Cycles {
		if c.Cycle == cycle {
			return c.VerifiedBytes > 0 && c.VerifiedBytes < c.SyncedBytes
		}
	}
	return false
}

func ResumeGate(outDir string, cycle int) bool {
	return resume_gate(outDir, cycle)
}
