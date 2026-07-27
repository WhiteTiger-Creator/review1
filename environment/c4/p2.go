package c4

import "vcp/k6"

func HoldInTransit(state map[string]any, shipment map[string]any) bool {
	facilities, _ := state["facilities"].(map[string]any)
	origin, _ := shipment["origin"].(string)
	batchID, _ := shipment["batch_id"].(string)
	doses, _ := shipment["doses"].(float64)
	fac := facility(facilities, origin)
	for _, b := range batchesOf(fac) {
		if b["batch_id"] != batchID {
			continue
		}
		st, _ := b["status"].(string)
		if st != "" && st != "usable" {
			continue
		}
		avail, _ := b["doses"].(float64)
		if avail < doses {
			return false
		}
		b["doses"] = avail - doses
		return true
	}
	return false
}

func ApplyDeliveries(state map[string]any) {
	shipments, _ := state["shipments"].([]map[string]any)
	facilities, _ := state["facilities"].(map[string]any)
	policy := k6.PolicyFromState(state)
	for _, s := range shipments {
		st, _ := s["status"].(string)
		if st != "delivered" && st != "quarantined" {
			continue
		}
		if applied, _ := s["applied"].(bool); applied {
			continue
		}
		dest, _ := s["destination"].(string)
		batchID, _ := s["batch_id"].(string)
		doses, _ := s["doses"].(float64)
		status := "usable"
		if policy.QuarantineMode == "honor_violation" {
			if st == "quarantined" {
				status = "quarantined"
			}
			if tempOk, ok := s["temp_ok"].(bool); ok && !tempOk {
				status = "quarantined"
			}
		}
		fac := facility(facilities, dest)
		batches, _ := fac["batches"].([]map[string]any)
		batches = append(batches, map[string]any{
			"batch_id":    batchID,
			"parent_id":   "",
			"split_gen":   0.0,
			"doses":       doses,
			"status":      status,
			"expires_day": float64(30),
		})
		fac["batches"] = batches
		s["applied"] = true
	}
	recompute_facility_totals(state)
}
