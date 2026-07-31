package main

import (
	"fmt"
	"os"

	"cdnqual/kilnemit"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: cdnqual run-forge --wire <path>")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "run-forge":
		os.Exit(runCast(os.Args[2:]))
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand %s\n", os.Args[1])
		os.Exit(2)
	}
}

func runCast(args []string) int {
	wire := ""
	for i := 0; i < len(args); i++ {
		if args[i] == "--wire" && i+1 < len(args) {
			wire = args[i+1]
			i++
		}
	}
	if wire == "" {
		fmt.Fprintln(os.Stderr, "run-forge requires --wire")
		return 2
	}
	if err := kilnemit.RunCast(wire); err != nil {
		fmt.Fprintf(os.Stderr, "run-forge: %v\n", err)
		return 1
	}
	return 0
}
