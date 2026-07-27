package k4

import (
	"encoding/json"
	"hxenv/lib/core"
	"strings"
)

func Tile(b []byte) (core.Tile, error) {
	var t core.Tile
	return t, json.Unmarshal(b, &t)
}

func Sum(b []byte) map[string]string {
	out := map[string]string{}
	for _, l := range strings.Split(string(b), "\n") {
		f := strings.Fields(l)
		if len(f) >= 3 {
			out[core.Key(f[0], f[1])] = f[2]
		}
	}
	return out
}

func Scraps(parts [][]byte) (map[string]core.Need, map[string]core.Change) {
	need := map[string]core.Need{}
	change := map[string]core.Change{}
	for _, b := range parts {
		local := map[string]core.Change{}
		for _, raw := range strings.Split(string(b), "\n") {
			s := strings.TrimSpace(raw)
			if i := strings.Index(s, "//"); i >= 0 {
				s = strings.TrimSpace(s[:i])
			}
			f := strings.Fields(s)
			if len(f) == 0 || s == "require (" || s == ")" {
				continue
			}
			if f[0] == "module" || f[0] == "go" {
				continue
			}
			if f[0] == "require" {
				f = f[1:]
			}
			if len(f) >= 2 && f[0] != "replace" && f[0] != "dropreplace" {
				need[core.Key(f[0], f[1])] = core.Need{ModulePath: f[0], Version: f[1]}
				continue
			}
			if len(f) >= 2 && f[0] == "dropreplace" {
				delete(local, f[1])
				continue
			}
			if len(f) >= 4 && f[0] == "replace" {
				i := 1
				if f[2] == "=>" {
					i = 3
				}
				if len(f) > i+1 {
					local[f[1]] = core.Change{From: f[1], To: f[i], ToVersion: f[i+1]}
				}
			}
		}
		if len(local) > 0 || len(parts) > 0 {
			change = local
		}
	}
	return need, change
}
