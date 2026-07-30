package ingest

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"wavellite_dc/paths"
	"wavellite_dc/q4"
)

func readJSONL(path string, decode func([]byte) error) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		if err := decode([]byte(line)); err != nil {
			return err
		}
	}
	return sc.Err()
}

func splitList(val string) []string {
	val = strings.TrimSpace(strings.Trim(strings.TrimSpace(val), "[]"))
	if val == "" {
		return []string{}
	}
	items := []string{}
	for _, raw := range strings.Split(val, ",") {
		item := strings.Trim(strings.TrimSpace(raw), "\"")
		if item != "" {
			items = append(items, item)
		}
	}
	return items
}

func parsePolicy(raw string) q4.Policy {
	pol := q4.Policy{
		AllowedFirmware: []string{},
		RequiredRoles:   []string{},
		AllowedClasses:  []string{},
		RegionWeights:   map[string]int{},
	}
	section := ""
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.Trim(line, "[]")
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		if section == "region_weights" {
			n, _ := strconv.Atoi(val)
			pol.RegionWeights[key] = n
			continue
		}
		switch key {
		case "eval_epoch":
			pol.EvalEpoch, _ = strconv.Atoi(val)
		case "min_nodes":
			pol.MinNodes, _ = strconv.Atoi(val)
		case "allowed_firmware":
			pol.AllowedFirmware = splitList(val)
		case "min_usable_tb":
			pol.MinUsableTB, _ = strconv.Atoi(val)
		case "min_replicas":
			pol.MinReplicas, _ = strconv.Atoi(val)
		case "min_gbps":
			pol.MinGbps, _ = strconv.Atoi(val)
		case "min_healthy_links":
			pol.MinHealthyLinks, _ = strconv.Atoi(val)
		case "min_roles":
			pol.MinRoles, _ = strconv.Atoi(val)
		case "required_roles":
			pol.RequiredRoles = splitList(val)
		case "cool_epochs":
			pol.CoolEpochs, _ = strconv.Atoi(val)
		case "budget_kw":
			pol.BudgetKW, _ = strconv.Atoi(val)
		case "allowed_classes":
			pol.AllowedClasses = splitList(val)
		}
	}
	return pol
}

func LoadBundle(name string) (q4.Bundle, error) {
	base := filepath.Join(paths.Root, "estate", "rosters", name)
	out := q4.Bundle{Name: name}
	polRaw, err := os.ReadFile(filepath.Join(base, "policy.toml"))
	if err != nil {
		return out, err
	}
	out.Policy = parsePolicy(string(polRaw))
	if err := readJSONL(filepath.Join(base, "units.jsonl"), func(b []byte) error {
		var row q4.Unit
		if err := json.Unmarshal(b, &row); err != nil {
			return err
		}
		out.Units = append(out.Units, row)
		return nil
	}); err != nil {
		return out, err
	}
	if err := readJSONL(filepath.Join(base, "approvals.jsonl"), func(b []byte) error {
		var row q4.Approval
		if err := json.Unmarshal(b, &row); err != nil {
			return err
		}
		out.Approvals = append(out.Approvals, row)
		return nil
	}); err != nil {
		return out, err
	}
	_ = readJSONL(filepath.Join(base, "maintenance.jsonl"), func(b []byte) error {
		var row q4.MaintRec
		if err := json.Unmarshal(b, &row); err != nil {
			return err
		}
		out.Maintenance = append(out.Maintenance, row)
		return nil
	})
	normalizeBundle(&out)
	return out, nil
}

func ListSites() ([]string, error) {
	raw, err := os.ReadFile(filepath.Join(paths.Root, "estate", "site_index.toml"))
	if err != nil {
		return nil, err
	}
	var names []string
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "name = ") {
			names = append(names, strings.Trim(strings.TrimPrefix(line, "name = "), "\""))
		}
	}
	return names, nil
}
