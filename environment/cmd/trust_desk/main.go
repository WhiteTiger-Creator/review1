package main

import (
	"flag"
	"fmt"
	"os"

	"core.net/fx/internal/harness"
)

func main() {
	pack := flag.String("pack", "/app/data/scenario_pack.json", "scenario pack path")
	out := flag.String("out", "/app/output", "output directory")
	root := flag.String("root", "/app", "application root")
	flag.Parse()
	if err := harness.RunMatrix(*root, *pack, *out); err != nil {
		fmt.Fprintf(os.Stderr, "trust_desk: %v\n", err)
		os.Exit(1)
	}
}
