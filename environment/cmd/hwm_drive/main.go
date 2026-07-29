package main

import (
	"flag"
	"fmt"
	"os"

	"environment/phase"
)

func main() {
	out := flag.String("out", "/app/output/peak_report.json", "graded report path")
	wide := flag.Bool("wide", false, "use wide budget arm")
	root := flag.String("root", "/app/environment", "environment root")
	flag.Parse()

	_ = phase.EmitHaze(*root)
	if err := phase.DriveMatrix(*root, *out, *wide); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
