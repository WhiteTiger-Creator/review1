package b7

import (
	"fmt"
	"vcp/k6"
)

var PlanShipments = plan_shipments
var ExecuteTransit = execute_transit
var FinalizeRecovery = finalize_recovery

func plan_shipments(state map[string]any, round int, plans []map[string]any) []map[string]any {
	out := []map[string]any{}
	for _, p := range plans {
		pr, _ := p["round"].(float64)
		if int(pr) != round {
			continue
		}
		shipment := map[string]any{
			"round":       float64(round),
			"shipment_id": p["shipment_id"],
			"origin":      p["origin"],
			"destination": p["destination"],
			"batch_id":    p["batch_id"],
			"doses":       p["doses"],
			"status":      "in_transit",
			"temp_ok":     true,
			"max_temp_c":  4.0,
		}
		out = append(out, shipment)
	}
	shipments, _ := state["shipments"].([]map[string]any)
	state["shipments"] = append(shipments, out...)
	return out
}

func execute_transit(state map[string]any, round int, shipment map[string]any, readingC float64, interrupt bool) {
	policy := k6.PolicyFromState(state)
	shipment["max_temp_c"] = readingC
	if readingC > policy.TempThresholdC {
		shipment["temp_ok"] = false
		logTemp(state, round, shipment, "violation")
	} else {
		shipment["temp_ok"] = true
		logTemp(state, round, shipment, "ok")
	}
	if interrupt {
		shipment["status"] = "interrupted"
		return
	}
	if tempOk, _ := shipment["temp_ok"].(bool); !tempOk {
		shipment["status"] = "quarantined"
	} else {
		shipment["status"] = "delivered"
	}
}

func finalize_recovery(state map[string]any, round int, shipmentID string) {
	shipments, _ := state["shipments"].([]map[string]any)
	for _, s := range shipments {
		if s["shipment_id"] != shipmentID {
			continue
		}
		st, _ := s["status"].(string)
		if st != "interrupted" {
			continue
		}
		policy := k6.PolicyFromState(state)
		if policy.TempOnRecovery == "preserve_transit" {
			maxTemp, _ := s["temp_c"].(float64)
			s["temp_ok"] = maxTemp <= policy.TempThresholdC
		} else {
			s["temp_ok"] = true
		}
		s["status"] = "recovered"
		logRecovery(state, round, s)
	}
}

func logTemp(state map[string]any, round int, shipment map[string]any, status string) {
	seq := nextSeq(state)
	sid, _ := shipment["shipment_id"].(string)
	reading, _ := shipment["max_temp_c"].(float64)
	line := fmt.Sprintf("SEQ=%d ROUND=%d EVENT=temp_check SHIPMENT=%s READING_C=%.1f STATUS=%s", seq, round, sid, reading, status)
	lines, _ := state["pending_log"].([]string)
	state["pending_log"] = append(lines, line)
}

func logRecovery(state map[string]any, round int, shipment map[string]any) {
	seq := nextSeq(state)
	sid, _ := shipment["shipment_id"].(string)
	line := fmt.Sprintf("SEQ=%d ROUND=%d EVENT=recovery SHIPMENT=%s STATUS=recovered", seq, round, sid)
	lines, _ := state["pending_log"].([]string)
	state["pending_log"] = append(lines, line)
}

func nextSeq(state map[string]any) int {
	seq, _ := state["seq"].(float64)
	state["seq"] = seq + 1
	return int(seq + 1)
}
