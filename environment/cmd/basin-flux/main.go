package main

import (
	"fmt"
	"os"
	"path/filepath"

	"basinflux/internal/b3t"
	"basinflux/internal/m7s"
	"basinflux/internal/q4c"
	"basinflux/internal/r9p"
)

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func main() {
	dataRoot := envOr("FLUX_DATA_ROOT", "/app/data")
	outPath := envOr("FLUX_OUTPUT", "/app/output/water_budget_report.json")
	cfgRoot := envOr("FLUX_CONFIG_ROOT", "/app/config")
	profile := envOr("FLUX_PROFILE", "basin")

	profilePath := filepath.Join(cfgRoot, profile+"-profile.toml")

	evidence, err := m7s.Load(dataRoot)
	if err != nil {
		fmt.Fprintf(os.Stderr, "evidence: %v\n", err)
		os.Exit(1)
	}

	cal, err := q4c.Resolve(profilePath, evidence)
	if err != nil {
		fmt.Fprintf(os.Stderr, "resolve: %v\n", err)
		os.Exit(1)
	}

	recharge, crop, err := b3t.IdentifyPair(evidence, cal)
	if err != nil {
		fmt.Fprintf(os.Stderr, "identify: %v\n", err)
		os.Exit(1)
	}
	cal = q4c.Reconcile(cal, recharge, crop)

	fluxes := b3t.Evaluate(evidence, cal)
	if err := r9p.Emit(outPath, evidence, fluxes, cal); err != nil {
		fmt.Fprintf(os.Stderr, "emit: %v\n", err)
		os.Exit(1)
	}
}
