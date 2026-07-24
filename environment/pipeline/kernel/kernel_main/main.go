package main

import (
	"encoding/json"
	"os"

	"tripfix/kernel/kernel_loader"
	"tripfix/kernel/kernel_verdict"
)

func main() {
	_, _ = loader.LoadAll("/app/feeds")
	decisions, totals, share := verdict.Decide(nil)
	out := map[string]any{
		"report_id":   "tripfix-v1",
		"decisions":   decisions,
		"totals":      totals,
		"route_share": share,
	}
	body, _ := json.MarshalIndent(out, "", "  ")
	_ = os.MkdirAll("/app/ledger", 0o755)
	_ = os.WriteFile("/app/ledger/output.json", body, 0o644)
}
