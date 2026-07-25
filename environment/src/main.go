package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: posixmatch <pattern> <subject>")
		os.Exit(2)
	}
	fmt.Println("NOMATCH")
	os.Exit(0)
}
