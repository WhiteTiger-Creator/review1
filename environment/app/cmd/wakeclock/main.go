package main

import (
	"fmt"
	"os"

	"wakeclock/internal/engine"
)

func main() {
	if err := engine.Run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "wakeclock: %v\n", err)
		os.Exit(1)
	}
}
