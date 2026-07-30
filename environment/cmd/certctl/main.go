package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"wavellite_dc/internal/run"
	"wavellite_dc/q4"
)

func main() {
	all := flag.Bool("all", false, "evaluate every site in the published index")
	site := flag.String("site", "", "evaluate a single published site")
	out := flag.String("out", "/app/output/certification_report.json", "report destination")
	flag.Parse()

	if !*all && *site == "" {
		fmt.Fprintln(os.Stderr, "certctl: choose --all or --site NAME")
		os.Exit(2)
	}

	if err := os.MkdirAll(filepath.Dir(*out), 0o755); err != nil {
		fmt.Fprintln(os.Stderr, "certctl:", err)
		os.Exit(1)
	}

	runner := run.RunAll
	if *site != "" {
		runner = func() (q4.Report, error) { return run.RunOne(*site) }
	}
	rep, err := runner()
	if err != nil {
		fmt.Fprintln(os.Stderr, "certctl:", err)
		os.Exit(1)
	}
	if err := run.WriteReport(*out, rep); err != nil {
		fmt.Fprintln(os.Stderr, "certctl:", err)
		os.Exit(1)
	}
	fmt.Printf("wrote %d row(s) to %s\n", len(rep.Sites), *out)
}
