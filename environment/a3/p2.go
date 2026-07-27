package a3

import "vcp/j4"

var LoadDemand = load_demand

func load_demand(root string, scenario string) (map[string]any, error) {
	path := root + "/f6/" + scenario + "_demand.json"
	return j4.ReadJSON(path)
}
