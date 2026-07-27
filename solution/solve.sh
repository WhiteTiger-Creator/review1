#!/usr/bin/env bash
set -euo pipefail

cat >"/app/environment/config/coldchain_policy.toml" <<'EOF'
[lineage]
parent_link_mode = "enforce_parent"
child_id_mode = "increment_generation"

[recovery]
temp_on_recovery = "preserve_transit"

[merge]
quarantine_mode = "honor_violation"
in_transit_release = "release"
EOF

cat >"/app/environment/a3/p1.go" <<'EOF_A3'
package a3

import (
	"fmt"
	"vcp/j4"
	"vcp/k6"
)

var LoadSeed = load_seed
var IngestProduction = ingest_production
var SplitBatch = split_batch

func load_seed(root string) (map[string]any, error) {
	facilities, err := j4.ReadJSON(root + "/h2/facilities.json")
	if err != nil {
		return nil, err
	}
	batches, err := j4.ReadJSON(root + "/h2/seed_batches.json")
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"facilities": facilities["facilities"],
		"batches":    batches["batches"],
	}, nil
}

func ingest_production(state map[string]any, round int, production map[string]any) {
	if production == nil {
		return
	}
	pr, _ := production["round"].(float64)
	if int(pr) != round {
		return
	}
	facilities, _ := state["facilities"].(map[string]any)
	batchID, _ := production["batch_id"].(string)
	facilityID, _ := production["facility_id"].(string)
	doses, _ := production["doses"].(float64)
	expires, _ := production["expires_day"].(float64)
	fac := facility(facilities, facilityID)
	batches := batchesOf(fac)
	entry := map[string]any{
		"batch_id":  batchID,
		"parent_id": "",
		"split_gen": 0,
		"doses":     doses,
		"status":    "usable",
		"expires_day": expires,
	}
	fac["batches"] = append(batches, entry)
	lineage := mapsOf(state, "lineage")
	state["lineage"] = append(lineage, map[string]any{
		"batch_id":  batchID,
		"parent_id": "",
		"split_gen": 0,
		"doses":     doses,
	})
}

func split_batch(state map[string]any, parentID, destFacility string, splitDoses int, round int) {
	facilities, _ := state["facilities"].(map[string]any)
	var parentFac map[string]any
	var parentBatch map[string]any
	for _, fac := range facilities {
		f, _ := fac.(map[string]any)
		for _, b := range batchesOf(f) {
			if b["batch_id"] != parentID {
				continue
			}
			st, _ := b["status"].(string)
			if st != "" && st != "usable" {
				continue
			}
			pd, _ := b["doses"].(float64)
			if int(pd) < splitDoses {
				continue
			}
			parentFac = f
			parentBatch = b
		}
	}
	if parentBatch == nil {
		return
	}
	pd, _ := parentBatch["doses"].(float64)
	if splitDoses <= 0 || int(pd) < splitDoses {
		return
	}
	parentBatch["doses"] = pd - float64(splitDoses)
	policy := k6.PolicyFromState(state)
	parentGen, _ := parentBatch["split_gen"].(float64)
	childGen := int(parentGen) + 1
	childID := fmt.Sprintf("%s-s%d", parentID, childGen)
	parentLink := parentID
	splitGen := float64(childGen)
	if policy.ChildIDMode != "increment_generation" {
		childGen = 0
		childID = fmt.Sprintf("%s-s0", parentID)
		splitGen = 0
	}
	if policy.ParentLinkMode != "enforce_parent" {
		parentLink = ""
	}
	child := map[string]any{
		"batch_id":    childID,
		"parent_id":   parentLink,
		"split_gen":   splitGen,
		"doses":       float64(splitDoses),
		"status":      parentBatch["status"],
		"expires_day": parentBatch["expires_day"],
	}
	dest := facility(facilities, destFacility)
	destBatches := batchesOf(dest)
	dest["batches"] = append(destBatches, child)
	lineage := mapsOf(state, "lineage")
	state["lineage"] = append(lineage, map[string]any{
		"batch_id": childID, "parent_id": parentLink, "split_gen": splitGen, "doses": float64(splitDoses),
	})
	logLine(state, round, fmt.Sprintf("EVENT=lineage PARENT=%s CHILD=%s SPLIT_GEN=%.0f DOSES=%d", parentID, childID, splitGen, splitDoses))
	_ = parentFac
}

func facility(facilities map[string]any, id string) map[string]any {
	if fac, ok := facilities[id].(map[string]any); ok {
		return fac
	}
	fac := map[string]any{"id": id, "usable_doses": 0.0, "quarantined_doses": 0.0, "batches": []map[string]any{}}
	facilities[id] = fac
	return fac
}

func mapsOf(state map[string]any, key string) []map[string]any {
	switch raw := state[key].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		state[key] = out
		return out
	default:
		return nil
	}
}

func batchesOf(fac map[string]any) []map[string]any {
	switch raw := fac["batches"].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		fac["batches"] = out
		return out
	default:
		return nil
	}
}

func logLine(state map[string]any, round int, body string) {
	seq := nextSeq(state)
	line := fmt.Sprintf("SEQ=%d ROUND=%d %s", seq, round, body)
	lines, _ := state["pending_log"].([]string)
	state["pending_log"] = append(lines, line)
}

func nextSeq(state map[string]any) int {
	seq, _ := state["seq"].(float64)
	state["seq"] = seq + 1
	return int(seq + 1)
}
EOF_A3

cat >"/app/environment/c4/p1.go" <<'EOF_C4'
package c4

import (
	"os"
	"vcp/j4"
	"vcp/k6"
)

var LoadCheckpoint = load_checkpoint
var SaveCheckpoint = save_checkpoint
var MergeRecovered = merge_recovered
var ApplyExpiry = apply_expiry
var RecomputeFacilityTotals = recompute_facility_totals

func load_checkpoint(path string, scenarioID string) (map[string]any, error) {
	if _, err := os.Stat(path); err != nil {
		return freshState(scenarioID), nil
	}
	data, err := j4.ReadJSON(path)
	if err != nil {
		return freshState(scenarioID), nil
	}
	prev, _ := data["scenario_id"].(string)
	if prev != scenarioID {
		return freshState(scenarioID), nil
	}
	return data, nil
}

func save_checkpoint(path string, state map[string]any) error {
	return j4.WriteJSON(path, state)
}

func merge_recovered(state map[string]any, round int) {
	shipments := shipmentsOf(state)
	facilities, _ := state["facilities"].(map[string]any)
	for _, s := range shipments {
		st, _ := s["status"].(string)
		if st != "recovered" {
			continue
		}
		if merged, _ := s["merged"].(bool); merged {
			continue
		}
		policy := k6.PolicyFromState(state)
		dest, _ := s["destination"].(string)
		fac := facility(facilities, dest)
		doses, _ := s["doses"].(float64)
		batchID, _ := s["batch_id"].(string)
		status := "usable"
		if policy.QuarantineMode == "honor_violation" {
			if tempOk, ok := s["temp_ok"].(bool); ok && !tempOk {
				status = "quarantined"
			}
			if maxTemp, ok := s["max_temp_c"].(float64); ok && maxTemp > policy.TempThresholdC {
				status = "quarantined"
			}
		}
		if policy.InTransitRelease == "skip" {
			origin, _ := s["origin"].(string)
			origFac := facility(facilities, origin)
			for _, ob := range batchesOf(origFac) {
				if ob["batch_id"] != batchID {
					continue
				}
				od, _ := ob["doses"].(float64)
				ob["doses"] = od + doses
			}
		}
		batches := batchesOf(fac)
		batches = append(batches, map[string]any{
			"batch_id":    batchID,
			"parent_id":   "",
			"split_gen":   0,
			"doses":       doses,
			"status":      status,
			"expires_day": float64(30),
		})
		fac["batches"] = batches
		s["merged"] = true
		s["applied"] = true
		_ = round
	}
	recompute_facility_totals(state)
}

func apply_expiry(state map[string]any, round int) {
	facilities, _ := state["facilities"].(map[string]any)
	for _, raw := range facilities {
		fac, _ := raw.(map[string]any)
		for _, b := range batchesOf(fac) {
			exp, _ := b["expires_day"].(float64)
			if int(exp) <= round {
				b["status"] = "expired"
			}
		}
	}
	recompute_facility_totals(state)
}

func recompute_facility_totals(state map[string]any) {
	facilities, _ := state["facilities"].(map[string]any)
	for _, raw := range facilities {
		fac, _ := raw.(map[string]any)
		usable := 0.0
		quarantined := 0.0
		for _, b := range batchesOf(fac) {
			d, _ := b["doses"].(float64)
			st, _ := b["status"].(string)
			switch st {
			case "quarantined":
				quarantined += d
			case "usable":
				usable += d
			}
		}
		fac["usable_doses"] = usable
		fac["quarantined_doses"] = quarantined
	}
}

func freshState(scenarioID string) map[string]any {
	return map[string]any{
		"schema_version": k6.SchemaVersion,
		"scenario_id":    scenarioID,
		"round":          0.0,
		"seq":            0.0,
		"facilities":     map[string]any{},
		"shipments":      []map[string]any{},
		"lineage":        []map[string]any{},
		"temp_log":       []map[string]any{},
		"pending_log":    []string{},
	}
}

func facility(facilities map[string]any, id string) map[string]any {
	if fac, ok := facilities[id].(map[string]any); ok {
		return fac
	}
	fac := map[string]any{"id": id, "usable_doses": 0.0, "quarantined_doses": 0.0, "batches": []map[string]any{}}
	facilities[id] = fac
	return fac
}

func shipmentsOf(state map[string]any) []map[string]any {
	switch raw := state["shipments"].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		state["shipments"] = out
		return out
	default:
		return nil
	}
}

func batchesOf(fac map[string]any) []map[string]any {
	switch raw := fac["batches"].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		fac["batches"] = out
		return out
	default:
		return nil
	}
}
EOF_C4

cat >"/app/environment/d9/p1.go" <<'EOF_D9'
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
	lineage := lineageOf(state)
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
		parts = append(parts, join(chunk, ";"))
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
	if lineage == nil {
		if raw, ok := inventory["lineage"].([]any); ok {
			lineage = make([]map[string]any, 0, len(raw))
			for _, item := range raw {
				if m, ok := item.(map[string]any); ok {
					lineage = append(lineage, m)
				}
			}
		}
	}
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
	switch raw := state["shipments"].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		state["shipments"] = out
		return out
	default:
		return nil
	}
}

func lineageOf(state map[string]any) []map[string]any {
	switch raw := state["lineage"].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		state["lineage"] = out
		return out
	default:
		return nil
	}
}

func pendingLog(state map[string]any) []string {
	switch raw := state["pending_log"].(type) {
	case []string:
		return raw
	case []any:
		out := make([]string, 0, len(raw))
		for _, item := range raw {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		state["pending_log"] = out
		return out
	default:
		return nil
	}
}

func batchesOf(fac map[string]any) []map[string]any {
	switch raw := fac["batches"].(type) {
	case []map[string]any:
		return raw
	case []any:
		out := make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		fac["batches"] = out
		return out
	default:
		return nil
	}
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
EOF_D9

# One-line recovery field correction (avoid whole-file rewrite of b7).
sed -i 's/s\["temp_c"\]/s["max_temp_c"]/' "/app/environment/b7/p1.go"

cd "/app/environment"
go build -o /app/bin/vcs_sim ./e5
