package main

import (
	"fmt"
	"os"
	"strconv"

	"blkmir/engine"
)

func main() {
	if len(os.Args) < 3 || os.Args[1] != "run" {
		fmt.Fprintln(os.Stderr, "usage: mirctl run <output-dir>")
		os.Exit(2)
	}
	root := os.Getenv("MIRROR_ROOT")
	if root == "" {
		root = "/app/environment"
	}
	cycle := 1
	if v := os.Getenv("CYCLE"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cycle = n
		}
	}
	appendMode := os.Getenv("APPEND_EXPORT") == "1"
	out := os.Args[2]
	if err := engine.RunCycle(root, out, cycle, appendMode); err != nil {
		fmt.Fprintf(os.Stderr, "mirctl: %v\n", err)
		os.Exit(1)
	}
}
