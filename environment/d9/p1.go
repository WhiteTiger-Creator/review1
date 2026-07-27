package d9

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strconv"
	"vcp/j4"
	"vcp/k6"
)

var ExportBundle = export_bundle

func export_bundle(state map[string]any) error {
	inventory := buildInventory(state)
	analytics := buildAnalytics(state, inventory)
	if err := j4.WriteJSON(k6.InventoryPath, inventory); err != nil {
		return err
	}
	if err := writeShipmentsCSV(state); err != nil {
		return err
	}
	if err := flushComplianceLog(state); err != nil {
		return err
	}
	return j4.WriteJSON(k6.AnalyticsPath, analytics)
}

func buildInventory(state map[string]any) map[string]any {
	digest := computeDigest(state)
	violations := countViolations(state)
	maxReading := maxTempReading(state)
	scenario, _ := state["scenario_id"].(string)
	round, _ := state["round"].(float64)
	lineage, _ := state["lineage"].([]map[string]any)
	facilities, _ := state["facilities"].(map[string]any)
	return map[string]any{
		"schema_version": k6.SchemaVersion,
		"scenario_id":    scenario,
		"round":          round,
		"facilities":     facilities,
		"lineage":        lineage,
		"temperature_summary": map[string]any{
			"max_reading_c": maxReading,
			"violations":    float64(violations),
		},
		"state_digest": digest,
	}
}

func buildAnalytics(state map[string]any, inventory map[string]any) map[string]any {
	usable := 0.0
	quarantined := 0.0
	facilities, _ := inventory["facilities"].(map[string]any)
	for _, raw := range facilities {
		fac, _ := raw.(map[string]any)
		u, _ := fac["usable_doses"].(float64)
		q, _ := fac["quarantined_doses"].(float64)
		usable += u
		quarantined += q
	}
	shipped, delivered := shipmentTotals(state)
	digest, _ := inventory["state_digest"].(string)
	compliance := compliancePass(state, inventory)
	return map[string]any{
		"total_usable_doses":      usable,
		"total_quarantined_doses": quarantined,
		"total_shipped":           shipped,
		"total_delivered":         delivered,
		"state_digest":            digest,
		"compliance_pass":         compliance,
	}
}

func writeShipmentsCSV(state map[string]any) error {
	header := []string{"round", "shipment_id", "origin", "destination", "batch_id", "doses", "status", "temp_ok"}
	rows := [][]string{}
	for _, s := range shipmentsOf(state) {
		round, _ := s["round"].(float64)
		doses, _ := s["doses"].(float64)
		tempOk, _ := s["temp_ok"].(bool)
		rows = append(rows, []string{
			strconv.Itoa(int(round)),
			strVal(s["shipment_id"]),
			strVal(s["origin"]),
			strVal(s["destination"]),
			strVal(s["batch_id"]),
			strconv.Itoa(int(doses)),
			strVal(s["status"]),
			strconv.FormatBool(tempOk),
		})
	}
	return j4.WriteCSV(k6.ShipmentsPath, header, rows)
}

func flushComplianceLog(state map[string]any) error {
	lines, _ := state["pending_log"].([]string)
	return j4.WriteLines(k6.CompliancePath, lines)
}

func computeDigest(state map[string]any) string {
	facilities, _ := state["facilities"].(map[string]any)
	keys := make([]string, 0, len(facilities))
	for k := range facilities {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := []string{}
	for _, fid := range keys {
		fac, _ := facilities[fid].(map[string]any)
		batches := batchesOf(fac)
		sort.Slice(batches, func(i, j int) bool {
			return strVal(batches[i]["batch_id"]) < strVal(batches[j]["batch_id"])
		})
		chunk := []string{}
		for _, b := range batches {
			chunk = append(chunk, fmt.Sprintf("%s|%s|%.0f|%s", fid, strVal(b["batch_id"]), num(b["doses"]), strVal(b["status"])))
		}
		parts = append(parts, fmt.Sprintf("%s:%s", fid, join(chunk, ";")))
	}
	raw := join(parts, "||")
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])[:16]
}

func compliancePass(state map[string]any, inventory map[string]any) bool {
	violations := countViolations(state)
	summary, _ := inventory["temperature_summary"].(map[string]any)
	v, _ := summary["violations"].(float64)
	if int(v) != violations {
		return false
	}
	lineage, _ := inventory["lineage"].([]map[string]any)
	for _, row := range lineage {
		child, _ := row["batch_id"].(string)
		parent, _ := row["parent_id"].(string)
		if parent != "" {
			splitGen, _ := row["split_gen"].(float64)
			if splitGen <= 0 {
				return false
			}
			if child != fmt.Sprintf("%s-s%.0f", parent, splitGen) {
				return false
			}
		}
	}
	return true
}

func countViolations(state map[string]any) int {
	n := 0
	for _, line := range pendingLog(state) {
		if contains(line, "STATUS=violation") {
			n++
		}
	}
	return n
}

func maxTempReading(state map[string]any) float64 {
	max := 0.0
	for _, s := range shipmentsOf(state) {
		if t, ok := s["max_temp_c"].(float64); ok && t > max {
			max = t
		}
	}
	return max
}

func shipmentTotals(state map[string]any) (float64, float64) {
	shipped := 0.0
	delivered := 0.0
	for _, s := range shipmentsOf(state) {
		d, _ := s["doses"].(float64)
		shipped += d
		st, _ := s["status"].(string)
		tempOk, _ := s["temp_ok"].(bool)
		if (st == "delivered" || st == "recovered") && tempOk {
			delivered += d
		}
	}
	return shipped, delivered
}

func shipmentsOf(state map[string]any) []map[string]any {
	raw, _ := state["shipments"].([]map[string]any)
	return raw
}

func pendingLog(state map[string]any) []string {
	raw, _ := state["pending_log"].([]string)
	return raw
}

func batchesOf(fac map[string]any) []map[string]any {
	raw, _ := fac["batches"].([]map[string]any)
	return raw
}

func strVal(v any) string {
	s, _ := v.(string)
	return s
}

func num(v any) float64 {
	n, _ := v.(float64)
	return n
}

func join(parts []string, sep string) string {
	out := ""
	for i, p := range parts {
		if i > 0 {
			out += sep
		}
		out += p
	}
	return out
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 || indexOf(s, sub) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
