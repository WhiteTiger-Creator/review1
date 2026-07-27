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
	shipments, _ := state["shipments"].([]map[string]any)
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
		origin, _ := s["origin"].(string)
		origFac := facility(facilities, origin)
		for _, ob := range batchesOf(origFac) {
			if ob["batch_id"] != batchID {
				continue
			}
			od, _ := ob["doses"].(float64)
			ob["doses"] = od + doses
		}
		batches, _ := fac["batches"].([]map[string]any)
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
		batches, _ := fac["batches"].([]map[string]any)
		for _, b := range batches {
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

func batchesOf(fac map[string]any) []map[string]any {
	raw, _ := fac["batches"].([]map[string]any)
	return raw
}
