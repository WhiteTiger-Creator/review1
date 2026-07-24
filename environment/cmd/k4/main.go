package main

import (
	"fmt"
	"os"

	"k4/eng"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "usage: k4 run --root DIR --out DIR\n")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "run":
		root, out := "", ""
		args := os.Args[2:]
		for i := 0; i < len(args); i++ {
			switch args[i] {
			case "--root":
				i++
				if i >= len(args) {
					fmt.Fprintf(os.Stderr, "need --root value\n")
					os.Exit(2)
				}
				root = args[i]
			case "--out":
				i++
				if i >= len(args) {
					fmt.Fprintf(os.Stderr, "need --out value\n")
					os.Exit(2)
				}
				out = args[i]
			default:
				fmt.Fprintf(os.Stderr, "unknown flag: %s\n", args[i])
				os.Exit(2)
			}
		}
		if root == "" || out == "" {
			fmt.Fprintf(os.Stderr, "need --root and --out\n")
			os.Exit(2)
		}
		if err := eng.RunAll(root, out); err != nil {
			fmt.Fprintf(os.Stderr, "run: %v\n", err)
			os.Exit(1)
		}
	default:
		fmt.Fprintf(os.Stderr, "unknown command\n")
		os.Exit(2)
	}
}
