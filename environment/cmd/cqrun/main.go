package main

import (
	"fmt"
	"os"

	"cqrun/run"
)

func main() {
	if len(os.Args) < 2 || os.Args[1] != "run" {
		fmt.Fprintf(os.Stderr, "usage: cqrun run --packs DIR --out FILE --state DIR\n")
		os.Exit(2)
	}
	packs := "/app/packs"
	out := "/app/output/cohort_trace.json"
	state := "/app/output/cohort_state"
	pol := "/app/docs/pol_a.toml"
	args := os.Args[2:]
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--packs":
			i++
			packs = args[i]
		case "--out":
			i++
			out = args[i]
		case "--state":
			i++
			state = args[i]
		case "--pol":
			i++
			pol = args[i]
		}
	}
	if err := run.Loop(packs, out, state, pol); err != nil {
		fmt.Fprintf(os.Stderr, "cqrun: %v\n", err)
		os.Exit(1)
	}
}
