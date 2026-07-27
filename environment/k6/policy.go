package k6

import (
	"os"
	"strings"
)

type Policy struct {
	ParentLinkMode   string
	ChildIDMode      string
	TempOnRecovery   string
	QuarantineMode   string
	InTransitRelease string
	TempThresholdC   float64
}

const PolicyPath = "/app/environment/config/coldchain_policy.toml"

func LoadPolicy(path string) Policy {
	defaults := Policy{
		ParentLinkMode:   "omit_parent",
		ChildIDMode:      "fixed_zero_suffix",
		TempOnRecovery:   "reset_ok",
		QuarantineMode:   "ignore_violation",
		InTransitRelease: "skip",
		TempThresholdC:   TempThresholdC,
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return defaults
	}
	current := ""
	policy := defaults
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			current = strings.Trim(line, "[]")
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"`)
		switch current {
		case "lineage":
			if key == "parent_link_mode" {
				policy.ParentLinkMode = val
			}
			if key == "child_id_mode" {
				policy.ChildIDMode = val
			}
		case "recovery":
			if key == "temp_on_recovery" {
				policy.TempOnRecovery = val
			}
		case "merge":
			if key == "quarantine_mode" {
				policy.QuarantineMode = val
			}
			if key == "in_transit_release" {
				policy.InTransitRelease = val
			}
		}
	}
	return policy
}

func PolicyFromState(state map[string]any) Policy {
	raw, ok := state["policy"].(map[string]any)
	if !ok {
		return LoadPolicy(PolicyPath)
	}
	p := Policy{TempThresholdC: TempThresholdC}
	if v, ok := raw["parent_link_mode"].(string); ok {
		p.ParentLinkMode = v
	}
	if v, ok := raw["child_id_mode"].(string); ok {
		p.ChildIDMode = v
	}
	if v, ok := raw["temp_on_recovery"].(string); ok {
		p.TempOnRecovery = v
	}
	if v, ok := raw["quarantine_mode"].(string); ok {
		p.QuarantineMode = v
	}
	if v, ok := raw["in_transit_release"].(string); ok {
		p.InTransitRelease = v
	}
	if v, ok := raw["temp_threshold_c"].(float64); ok {
		p.TempThresholdC = v
	}
	return p
}

func PolicyToMap(p Policy) map[string]any {
	return map[string]any{
		"parent_link_mode":   p.ParentLinkMode,
		"child_id_mode":      p.ChildIDMode,
		"temp_on_recovery":   p.TempOnRecovery,
		"quarantine_mode":    p.QuarantineMode,
		"in_transit_release": p.InTransitRelease,
		"temp_threshold_c":   p.TempThresholdC,
	}
}
