package main

import (
	"fmt"
	"os"

	"nubx/drvx/internal/cert"
	"nubx/drvx/internal/synth"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: drvx synth|certify ...")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "synth":
		annex, out := flagVal(os.Args[2:], "--annex"), flagVal(os.Args[2:], "--out")
		if annex == "" || out == "" {
			fatal("synth requires --annex and --out")
		}
		if err := synth.Run(annex, out); err != nil {
			fatal(err.Error())
		}
	case "certify":
		tr, rep := flagVal(os.Args[2:], "--transcript"), flagVal(os.Args[2:], "--report")
		if tr == "" || rep == "" {
			fatal("certify requires --transcript and --report")
		}
		if err := cert.Run(tr, rep); err != nil {
			fatal(err.Error())
		}
	default:
		fatal("unknown command")
	}
}

func flagVal(args []string, name string) string {
	for i := 0; i+1 < len(args); i++ {
		if args[i] == name {
			return args[i+1]
		}
	}
	return ""
}

func fatal(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}
