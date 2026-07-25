// Command privhelper is the privileged helper dispatcher entry point. It parses
// the command line and delegates to the cli package.
package main

import (
	"fmt"
	"os"

	"privhelper/internal/cli"
)

func main() {
	if err := cli.Run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "privhelper:", err)
		os.Exit(1)
	}
}
