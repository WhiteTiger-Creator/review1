package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

func evaluate(line string) string {
	return "UNIMPLEMENTED"
}

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: tsuro <input> <output>")
		os.Exit(2)
	}
	in, err := os.Open(os.Args[1])
	if err != nil {
		os.Exit(1)
	}
	defer in.Close()
	out, err := os.Create(os.Args[2])
	if err != nil {
		os.Exit(1)
	}
	defer out.Close()
	w := bufio.NewWriter(out)
	defer w.Flush()
	sc := bufio.NewScanner(in)
	sc.Buffer(make([]byte, 1024*1024), 1024*1024)
	for sc.Scan() {
		line := strings.TrimRight(sc.Text(), "\r")
		if strings.TrimSpace(line) == "" {
			continue
		}
		fmt.Fprintln(w, evaluate(line))
	}
}
