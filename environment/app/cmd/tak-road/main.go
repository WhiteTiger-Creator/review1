package main

import (
	"flag"
	"fmt"
	"os"

	"takroad/internal/board"
	"takroad/internal/bracket"
	"takroad/internal/season"
	"takroad/internal/victory"
)

func main() {
	scenariosDir := flag.String("scenarios", "/app/scenarios", "championship scenario directory")
	configDir := flag.String("config", "/app/config", "rules config directory")
	outDir := flag.String("out", "/app/output", "report output directory")
	flag.Parse()

	rules, err := season.LoadRules(*configDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "config: %v\n", err)
		os.Exit(1)
	}
	scenarios, err := board.LoadScenarios(*scenariosDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "scenarios: %v\n", err)
		os.Exit(1)
	}

	var matches []bracket.MatchRow
	for _, sc := range scenarios {
		out := victory.Decide(sc.Cells, rules)
		matches = append(matches, bracket.BuildMatch(sc.MatchID, sc.PlayerA, sc.PlayerB, out, rules))
	}

	if err := bracket.WriteReport(*outDir, rules, matches); err != nil {
		fmt.Fprintf(os.Stderr, "report: %v\n", err)
		os.Exit(1)
	}
}
