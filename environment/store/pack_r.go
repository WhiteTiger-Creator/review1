package store

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func readLaneCfg(root string) LaneCfg {
	lanes := LaneCfg{CatalogLane: 0, ProbeLane: 1}
	path := filepath.Join(root, "config", "epoch_lane.toml")
	b, err := os.ReadFile(path)
	if err != nil {
		return lanes
	}
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val, err := strconv.Atoi(strings.TrimSpace(parts[1]))
		if err != nil {
			continue
		}
		switch key {
		case "catalog_lane":
			lanes.CatalogLane = val
		case "probe_lane":
			lanes.ProbeLane = val
		}
	}
	return lanes
}

func pack_r(root string, cat CatFixture, prb PrbFixture, seal int) (int, int) {
	lanes := readLaneCfg(root)
	lanes.ProbeLane = lanes.CatalogLane
	return lane_s(cat, prb, lanes, seal)
}
