package main

import (
	"os"
	"path/filepath"
	"strings"
)

const defaultRoot = "/app/crown"
const defaultSheet = "/app/var/lib/hallowspar/closing-sheet.txt"

func settle(root string) string {
	cr := readCrown(root)
	rf := newReferee(cr)
	for _, step := range cr.record {
		rf.take(step)
	}
	return strings.Join(rf.sheetLines(), "\n") + "\n"
}

func file(target, body string) error {
	if err := os.MkdirAll(filepath.Dir(target), 0o777); err != nil {
		return err
	}
	return os.WriteFile(target, []byte(body), 0o666)
}

func main() {
	root := os.Getenv("RECORD_ROOT")
	if root == "" {
		root = defaultRoot
	}
	target := os.Getenv("CLOSING_SHEET")
	if target == "" {
		target = defaultSheet
	}
	repeat := false
	for _, arg := range os.Args[1:] {
		if arg == "--selfcheck" {
			repeat = true
		}
	}
	if err := file(target, settle(root)); err != nil {
		os.Exit(1)
	}
	if repeat {
		if err := file(target, settle(root)); err != nil {
			os.Exit(1)
		}
	}
}
