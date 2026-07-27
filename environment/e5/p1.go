package main

import (
	"fmt"
	"os"
	"path/filepath"
	"vcp/a3"
	"vcp/b7"
	"vcp/c4"
	"vcp/d9"
	"vcp/j4"
	"vcp/k6"
)

func main() {
	scenario, rounds, err := parseArgs(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := runScenario(scenario, rounds); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func parseArgs(args []string) (string, int, error) {
	if len(args) < 3 || args[0] != "run" || args[1] != "--scenario" {
		return "", 0, fmt.Errorf("usage: /app/bin/vcs_sim run --scenario <id> [--rounds N]")
	}
	scenario := args[2]
	rounds := 0
	for i := 3; i < len(args); i++ {
		if args[i] == "--rounds" && i+1 < len(args) {
			fmt.Sscanf(args[i+1], "%d", &rounds)
			i++
		}
	}
	return scenario, rounds, nil
}

func runScenario(scenarioID string, roundOverride int) error {
	root := k6.EnvRoot
	cfgPath := filepath.Join(root, "scenarios", scenarioID+".json")
	cfg, err := j4.ReadJSON(cfgPath)
	if err != nil {
		return err
	}
	state, err := c4.LoadCheckpoint(k6.CheckpointPath, scenarioID)
	if err != nil {
		return err
	}
	policy := k6.LoadPolicy(k6.PolicyPath)
	state["policy"] = k6.PolicyToMap(policy)
	seed, err := a3.LoadSeed(root)
	if err != nil {
		return err
	}
	if state["round"] == 0.0 || len(mapKeys(state["facilities"])) == 0 {
		state["facilities"] = seed["facilities"]
		for _, b := range seedBatches(seed) {
			fid, _ := b["facility_id"].(string)
			fac := mapFac(state, fid)
			batches, _ := fac["batches"].([]map[string]any)
			entry := map[string]any{
				"batch_id":    b["batch_id"],
				"parent_id":   "",
				"split_gen":   0,
				"doses":       b["doses"],
				"status":      "usable",
				"expires_day": b["expires_day"],
			}
			fac["batches"] = append(batches, entry)
			lineage, _ := state["lineage"].([]map[string]any)
			state["lineage"] = append(lineage, map[string]any{
				"batch_id": b["batch_id"], "parent_id": "", "split_gen": 0, "doses": b["doses"],
			})
		}
	}
	plans, _ := cfg["shipments"].([]any)
	rounds, _ := cfg["rounds"].(float64)
	total := int(rounds)
	if roundOverride > 0 {
		total = roundOverride
	}
	startRound := int(state["round"].(float64))
	if startRound == 0 {
		startRound = 1
	} else {
		startRound++
	}
	for round := startRound; round <= total; round++ {
		state["round"] = float64(round)
		if prod := cfgProduction(cfg, round); prod != nil {
			a3.IngestProduction(state, round, prod)
		}
		for _, raw := range plans {
			plan, _ := raw.(map[string]any)
			pr, _ := plan["round"].(float64)
			if int(pr) != round {
				continue
			}
			created := b7.PlanShipments(state, round, []map[string]any{plan})
			for _, shipment := range created {
				if !c4.HoldInTransit(state, shipment) {
					continue
				}
				reading := planReading(plan, cfg, round)
				interrupt := planInterrupt(plan, round)
				b7.ExecuteTransit(state, round, shipment, reading, interrupt)
			}
		}
		c4.ApplyDeliveries(state)
		if sr, ok := cfg["split_round"].(float64); ok && int(sr) == round {
			parent, _ := cfg["split_batch"].(string)
			dest, _ := cfg["split_dest"].(string)
			doses, _ := cfg["split_doses"].(float64)
			a3.SplitBatch(state, parent, dest, int(doses), round)
		}
		if rr, ok := cfg["recovery_round"].(float64); ok && int(rr) == round {
			sid, _ := cfg["recovery_shipment"].(string)
			b7.FinalizeRecovery(state, round, sid)
			c4.MergeRecovered(state, round)
		}
		c4.ApplyExpiry(state, round)
		c4.RecomputeFacilityTotals(state)
		if err := c4.SaveCheckpoint(k6.CheckpointPath, state); err != nil {
			return err
		}
	}
	return d9.ExportBundle(state)
}

func cfgProduction(cfg map[string]any, round int) map[string]any {
	raw, ok := cfg["production"].(map[string]any)
	if !ok {
		return nil
	}
	pr, _ := raw["round"].(float64)
	if int(pr) == round {
		return raw
	}
	return nil
}

func planReading(plan map[string]any, cfg map[string]any, round int) float64 {
	if tr, ok := plan["temp_c"].(float64); ok {
		return tr
	}
	if er, ok := cfg["excursion_round"].(float64); ok && int(er) == round {
		if temp, ok := cfg["excursion_temp_c"].(float64); ok {
			return temp
		}
	}
	return 4.0
}

func planInterrupt(plan map[string]any, round int) bool {
	if ir, ok := plan["interrupt"].(bool); ok && ir {
		return true
	}
	return false
}

func seedBatches(seed map[string]any) []map[string]any {
	raw, _ := seed["batches"].([]any)
	out := []map[string]any{}
	for _, item := range raw {
		m, _ := item.(map[string]any)
		out = append(out, m)
	}
	return out
}

func mapFac(state map[string]any, id string) map[string]any {
	facilities, _ := state["facilities"].(map[string]any)
	if fac, ok := facilities[id].(map[string]any); ok {
		return fac
	}
	fac := map[string]any{"id": id, "usable_doses": 0.0, "quarantined_doses": 0.0, "batches": []map[string]any{}}
	facilities[id] = fac
	return fac
}

func mapKeys(v any) []string {
	m, _ := v.(map[string]any)
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}
