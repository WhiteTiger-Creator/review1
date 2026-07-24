package main

import (
	"fmt"
	"os"

	"scepca/internal/scep"
)

func usage() {
	fmt.Fprintln(os.Stderr, "usage: scepd <enroll REQUEST.json | ca-info>")
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	switch os.Args[1] {
	case "enroll":
		if len(os.Args) < 3 {
			usage()
			os.Exit(2)
		}
		runEnroll(os.Args[2])
	case "ca-info":
		runCAInfo()
	default:
		usage()
		os.Exit(2)
	}
}

func runEnroll(path string) {
	req, err := scep.LoadRequest(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, err.Error())
		os.Exit(1)
	}

	authority := scep.NewAuthority()
	resp, err := authority.PKIOperation(req)
	if err != nil {
		fmt.Fprintln(os.Stderr, err.Error())
		os.Exit(1)
	}

	fmt.Println(resp.String())
}

func runCAInfo() {
	authority := scep.NewAuthority()
	fmt.Print(authority.Info())
}
