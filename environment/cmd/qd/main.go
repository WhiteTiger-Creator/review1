package main

import (
	"fmt"
	"os"

	"qdenv/gw"
	"qdenv/q9"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: qd play|scan")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "play":
		runPlay(os.Args[2:])
	case "scan":
		runScan(os.Args[2:])
	default:
		fmt.Fprintln(os.Stderr, "unknown subcommand")
		os.Exit(2)
	}
}

func runPlay(args []string) {
	lane := ""
	for i := 0; i < len(args); i++ {
		if args[i] == "--lane" && i+1 < len(args) {
			lane = args[i+1]
			break
		}
	}
	if lane == "" {
		fmt.Fprintln(os.Stderr, "missing --lane")
		os.Exit(2)
	}
	m, err := q9.LoadLane(lane)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	lines, tbl := gw.RunLane(m)
	if err := q9.WriteOutputs(lines, tbl, m.ID, "/app/output"); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func runScan(args []string) {
	lane := ""
	for i := 0; i < len(args); i++ {
		if args[i] == "--lane" && i+1 < len(args) {
			lane = args[i+1]
			break
		}
	}
	if lane == "" {
		fmt.Fprintln(os.Stderr, "missing --lane")
		os.Exit(2)
	}
	if err := gw.WriteScanStatus(lane); err != nil {
		os.Exit(1)
	}
	os.Exit(gw.ScanExit(lane))
}
