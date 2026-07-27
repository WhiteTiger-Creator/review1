package main

import (
	"fmt"
	"os"

	"k4/eng"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "usage: k4 fit-score|run|recover --root DIR --out DIR\n")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "fit-score", "run":
		root, out, err := parseRootOut(os.Args[2:])
		if err != nil {
			fmt.Fprintf(os.Stderr, "%v\n", err)
			os.Exit(2)
		}
		if err := eng.FitCheckpoint(root); err != nil {
			fmt.Fprintf(os.Stderr, "fit: %v\n", err)
			os.Exit(1)
		}
		if err := eng.RunAll(root, out); err != nil {
			fmt.Fprintf(os.Stderr, "score: %v\n", err)
			os.Exit(1)
		}
	case "recover":
		root, out, err := parseRootOut(os.Args[2:])
		if err != nil {
			fmt.Fprintf(os.Stderr, "%v\n", err)
			os.Exit(2)
		}
		if err := eng.RecoverAll(root, out); err != nil {
			fmt.Fprintf(os.Stderr, "recover: %v\n", err)
			os.Exit(1)
		}
	default:
		fmt.Fprintf(os.Stderr, "unknown command\n")
		os.Exit(2)
	}
}

func parseRootOut(args []string) (string, string, error) {
	root, out := "", ""
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--root":
			i++
			if i >= len(args) {
				return "", "", fmt.Errorf("need --root value")
			}
			root = args[i]
		case "--out":
			i++
			if i >= len(args) {
				return "", "", fmt.Errorf("need --out value")
			}
			out = args[i]
		default:
			return "", "", fmt.Errorf("unknown flag: %s", args[i])
		}
	}
	if root == "" || out == "" {
		return "", "", fmt.Errorf("need --root and --out")
	}
	return root, out, nil
}
