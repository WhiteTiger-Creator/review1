package main

import (
	"encoding/json"
	"os"
)

func main() {
	_ = os.MkdirAll("/app/output", 0755)
	report := map[string]any{
		"results": []any{},
		"final": map[string]any{
			"status": "ongoing",
			"winner": nil,
			"legal_moves": 0,
			"no_progress": 0,
			"ejections": map[string]int{},
			"next_player": nil,
			"position_key": "",
			"board": []any{},
		},
	}
	data, _ := json.MarshalIndent(report, "", "  ")
	_ = os.WriteFile("/app/output/report.json", data, 0644)
}
