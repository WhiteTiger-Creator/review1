package load

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	_ "time/tzdata"

	"wakeclock/internal/model"
)

func Units(dir string) ([]model.Unit, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var units []model.Unit
	seen := map[string]bool{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".timer.json") {
			continue
		}
		var unit model.Unit
		if err := Object(filepath.Join(dir, entry.Name()), &unit); err != nil {
			return nil, err
		}
		if unit.SchemaVersion != "wakeclock.unit.v1" || unit.UnitID == "" || seen[unit.UnitID] || unit.Hour < 0 || unit.Hour > 23 || unit.Minute < 0 || unit.Minute > 59 || len(unit.Weekdays) == 0 || unit.RandomDelaySec < 0 || unit.AccuracySec < 0 || unit.CatchUpCap < 1 || unit.Salt == "" {
			return nil, fmt.Errorf("invalid unit %s", entry.Name())
		}
		if _, err := time.LoadLocation(unit.Timezone); err != nil {
			return nil, fmt.Errorf("invalid timezone")
		}
		seen[unit.UnitID] = true
		units = append(units, unit)
	}
	if len(units) == 0 {
		return nil, fmt.Errorf("no units")
	}
	sort.Slice(units, func(i, j int) bool { return units[i].UnitID < units[j].UnitID })
	for _, unit := range units {
		for _, dep := range unit.DependsOn {
			if !seen[dep] || dep == unit.UnitID {
				return nil, fmt.Errorf("invalid dependency")
			}
		}
	}
	if err := validateAcyclic(units); err != nil {
		return nil, err
	}
	return units, nil
}

func validateAcyclic(units []model.Unit) error {
	deps := map[string][]string{}
	for _, unit := range units {
		deps[unit.UnitID] = unit.DependsOn
	}
	state := map[string]int{}
	var visit func(string) error
	visit = func(id string) error {
		if state[id] == 1 {
			return fmt.Errorf("dependency cycle")
		}
		if state[id] == 2 {
			return nil
		}
		state[id] = 1
		for _, dep := range deps[id] {
			if err := visit(dep); err != nil {
				return err
			}
		}
		state[id] = 2
		return nil
	}
	for id := range deps {
		if err := visit(id); err != nil {
			return err
		}
	}
	return nil
}
