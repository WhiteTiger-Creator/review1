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
	batches, _ := fac["batches"].([]map[string]any)
	entry := map[string]any{
		"batch_id":  batchID,
		"parent_id": "",
		"split_gen": 0,
		"doses":     doses,
		"status":    "usable",
		"expires_day": expires,
	}
	fac["batches"] = append(batches, entry)
	lineage, _ := state["lineage"].([]map[string]any)
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
	childGen := int(parentGen)
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
	destBatches, _ := dest["batches"].([]map[string]any)
	dest["batches"] = append(destBatches, child)
	lineage, _ := state["lineage"].([]map[string]any)
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

func batchesOf(fac map[string]any) []map[string]any {
	raw, _ := fac["batches"].([]map[string]any)
	return raw
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
