package verdict

import "tripfix/kernel/kernel_loader"

type Decision struct {
	Feed       string `json:"feed"`
	TripID     string `json:"trip_id"`
	RouteID    string `json:"route_id"`
	ReceivedTS string `json:"received_ts"`
	Verdict    string `json:"verdict"`
	Ordinal    int    `json:"ordinal"`
}

func Decide(_ []loader.Record) ([]Decision, map[string]int, map[string]int) {
	return []Decision{}, map[string]int{}, map[string]int{}
}
