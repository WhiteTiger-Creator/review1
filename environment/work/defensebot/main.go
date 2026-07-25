package main

import (
	"bufio"
	"encoding/json"
	"os"
)

// Baseline bot: legal local reactions and simple STATUS signals only.
// Strategically weak: does not track belief, partner intent, or power reservation.
func main() {
	sc := bufio.NewScanner(os.Stdin)
	buf := make([]byte, 0, 64*1024)
	sc.Buffer(buf, 1024*1024)
	enc := json.NewEncoder(os.Stdout)
	tokensUsed := 0
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
		sector, _ := msg["sector"].(string)
		budget := intFrom(msg["signal_budget"])
		tokensLeft := intFrom(msg["signal_tokens"])
		actions := []map[string]any{}

		contacts, _ := msg["contacts"].([]any)
		if len(contacts) > 0 {
			c0, _ := contacts[0].(map[string]any)
			cSector, _ := c0["sector"].(string)
			cID, _ := c0["id"].(string)
			if cSector == sector {
				actions = append(actions, map[string]any{"op": "intercept", "contact": cID, "target": cSector})
			} else if cSector != "" {
				actions = append(actions, map[string]any{"op": "scan", "target": cSector})
				actions = append(actions, map[string]any{"op": "move", "target": cSector})
			}
		} else {
			actions = append(actions, map[string]any{"op": "hold"})
		}

		// Occasional STATUS only — no WARN/ACK/SYNC intelligence.
		if tokensLeft > 0 && budget > 0 && tokensUsed < 1 && round%4 == 1 {
			actions = append(actions, map[string]any{
				"op": "signal",
				"msg": map[string]any{"type": "STATUS", "sector": sector},
			})
			tokensUsed++
		}

		if len(actions) == 0 {
			actions = []map[string]any{{"op": "hold"}}
		}
		_ = enc.Encode(map[string]any{
			"type":    "orders",
			"round":   round,
			"actions": actions,
		})
	}
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
