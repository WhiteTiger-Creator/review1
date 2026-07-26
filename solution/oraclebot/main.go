package main

import (
	"bufio"
	"encoding/json"
	"os"
	"sort"
)

// Oracle: belief tracking, signal-value estimation, partner-intent inference,
// power reservation, coverage planning, synchronized interception, deterministic ties.
func main() {
	sc := bufio.NewScanner(os.Stdin)
	buf := make([]byte, 0, 64*1024)
	sc.Buffer(buf, 1024*1024)
	enc := json.NewEncoder(os.Stdout)

	belief := map[string]map[string]any{}
	partnerCover := map[string]int{}
	pendingAck := []map[string]any{}
	syncArmedRound := -1
	warned := map[string]int{}

	for sc.Scan() {
		var msg map[string]any
		if err := json.Unmarshal(sc.Bytes(), &msg); err != nil {
			continue
		}
		typ, _ := msg["type"].(string)
		if typ == "end" {
			_ = enc.Encode(map[string]any{"type": "end_ack"})
			return
		}
		if typ != "observation" {
			continue
		}

		round := intFrom(msg["round"])
		sector := str(msg["sector"])
		available := intFrom(msg["power_available"])
		tokensLeft := intFrom(msg["signal_tokens"])
		jammed := boolFrom(msg["jammed"])
		maxActions := intFrom(msg["max_actions"])
		if maxActions <= 0 {
			maxActions = 4
		}
		partnerSector := str(msg["partner_public_sector"])
		horizon := intFrom(msg["horizon"])

		contacts := asMaps(msg["contacts"])
		sort.Slice(contacts, func(i, j int) bool { return str(contacts[i]["id"]) < str(contacts[j]["id"]) })
		for _, c := range contacts {
			belief[str(c["id"])] = c
		}

		signals := asMaps(msg["signals_in"])
		sort.Slice(signals, func(i, j int) bool { return str(signals[i]["id"]) < str(signals[j]["id"]) })
		for _, s := range signals {
			stype := str(s["type"])
			switch stype {
			case "WARN_LANE", "COVER":
				cid := str(s["contact"])
				if cid != "" {
					partnerCover[cid] = round
				}
				pendingAck = append(pendingAck, s)
			case "SYNC_CAPTURE":
				syncArmedRound = round
				pendingAck = append(pendingAck, s)
			case "NEED_POWER":
				// partner conserving — leave generator headroom
			}
		}

		actions := []map[string]any{}
		powerLeft := available
		// Reserve 3 for late-wave intercept when horizon remaining is large and doctrine cues NEED_POWER history
		reserve := 0
		if horizon-round >= 3 && available <= 4 {
			reserve = 1
		}
		powerLeft -= reserve
		if powerLeft < 0 {
			powerLeft = available
		}

		push := func(a map[string]any, cost int) bool {
			if len(actions) >= maxActions {
				return false
			}
			if cost > powerLeft {
				return false
			}
			actions = append(actions, a)
			powerLeft -= cost
			return true
		}

		// ACK delayed partner warnings
		if tokensLeft > 0 && len(pendingAck) > 0 && !jammed && len(actions) < maxActions {
			ref := pendingAck[0]
			pendingAck = pendingAck[1:]
			actions = append(actions, map[string]any{
				"op": "signal",
				"msg": map[string]any{
					"type": "ACK", "sector": str(ref["sector"]),
					"contact": str(ref["contact"]), "ref": str(ref["id"]),
				},
			})
			tokensLeft--
		}

		gens := asMaps(msg["generators"])
		for _, g := range gens {
			if boolFrom(g["damaged"]) || boolFrom(g["overload"]) {
				push(map[string]any{"op": "repair", "target": "linked"}, 2)
				break
			}
		}

		civSet := flattenCorridors(msg["civilian_corridors"])

		var falseIDs = map[string]bool{}
		var targets []map[string]any
		for _, c := range contacts {
			id := str(c["id"])
			if boolFrom(c["false_likely"]) || str(c["kind_guess"]) == "false" {
				falseIDs[id] = true
				continue
			}
			targets = append(targets, c)
		}
		sort.Slice(targets, func(i, j int) bool { return str(targets[i]["id"]) < str(targets[j]["id"]) })

		// Shield civilians under pressure before optional scans
		for _, c := range targets {
			sec := str(c["sector"])
			if civSet[sec] {
				if push(map[string]any{"op": "shield", "target": sec}, 2) {
					if tokensLeft > 0 && powerLeft < 3 && len(actions) < maxActions {
						actions = append(actions, map[string]any{
							"op": "signal", "msg": map[string]any{"type": "CANCEL_SCAN", "sector": sec},
						})
						tokensLeft--
					}
				}
				break
			}
		}

		// Sync capture for boss
		if b, ok := belief["boss"]; ok && !falseIDs["boss"] {
			bsec := str(b["sector"])
			if syncArmedRound < 0 && tokensLeft > 0 && round >= 4 && len(actions) < maxActions {
				actions = append(actions, map[string]any{
					"op": "signal",
					"msg": map[string]any{"type": "SYNC_CAPTURE", "sector": bsec, "contact": "boss"},
				})
				tokensLeft--
				syncArmedRound = round
			}
			if syncArmedRound >= 0 {
				if bsec != sector {
					push(map[string]any{"op": "move", "target": bsec}, 1)
				}
				push(map[string]any{"op": "intercept", "contact": "boss", "target": bsec}, 3)
			}
		}

		// Warn partner about confirmed/likely threats away from them
		for _, c := range targets {
			if tokensLeft <= 0 || len(actions) >= maxActions {
				break
			}
			id := str(c["id"])
			sec := str(c["sector"])
			if warned[id] >= round-1 {
				continue
			}
			if boolFrom(c["confirmed"]) && sec != partnerSector {
				actions = append(actions, map[string]any{
					"op": "signal",
					"msg": map[string]any{"type": "WARN_LANE", "sector": sec, "contact": id},
				})
				tokensLeft--
				warned[id] = round
				break
			}
		}

		// Cover threats: skip false; skip if partner already covering same sector/contact
		for _, c := range targets {
			id := str(c["id"])
			sec := str(c["sector"])
			if id == "boss" && syncArmedRound >= 0 {
				continue
			}
			if partnerCover[id] >= round && partnerSector == sec {
				continue
			}
			// Scan to confirm unknowns first when power allows
			if !boolFrom(c["confirmed"]) && str(c["kind_guess"]) == "unknown" {
				push(map[string]any{"op": "scan", "target": sec}, 2)
			}
			if sec != sector {
				push(map[string]any{"op": "move", "target": sec}, 1)
			}
			if !falseIDs[id] {
				push(map[string]any{"op": "intercept", "contact": id, "target": sec}, 3)
			}
			if len(actions) >= maxActions {
				break
			}
		}

		// Proactive hub scan when no contacts (search)
		if len(contacts) == 0 && powerLeft >= 2 && len(actions) < maxActions {
			for _, g := range gens {
				gs := str(g["sector"])
				if gs != "" {
					push(map[string]any{"op": "scan", "target": gs}, 2)
					break
				}
			}
		}

		if len(actions) == 0 {
			actions = append(actions, map[string]any{"op": "hold"})
		}
		if len(actions) > maxActions {
			actions = actions[:maxActions]
		}
		_ = enc.Encode(map[string]any{"type": "orders", "round": round, "actions": actions})
	}
}

func flattenCorridors(v any) map[string]bool {
	out := map[string]bool{}
	arr, ok := v.([]any)
	if !ok {
		return out
	}
	for _, row := range arr {
		switch t := row.(type) {
		case []any:
			for _, x := range t {
				out[str(x)] = true
			}
		}
	}
	return out
}

func asMaps(v any) []map[string]any {
	arr, ok := v.([]any)
	if !ok {
		return nil
	}
	out := make([]map[string]any, 0, len(arr))
	for _, x := range arr {
		if m, ok := x.(map[string]any); ok {
			out = append(out, m)
		}
	}
	return out
}

func str(v any) string {
	s, _ := v.(string)
	return s
}

func intFrom(v any) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	default:
		return 0
	}
}

func boolFrom(v any) bool {
	b, _ := v.(bool)
	return b
}
