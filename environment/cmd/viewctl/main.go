package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"blkmir/store"
)

func main() {
	if len(os.Args) < 2 || os.Args[1] != "show" {
		fmt.Fprintln(os.Stderr, "usage: viewctl show")
		os.Exit(2)
	}
	root := os.Getenv("MIRROR_ROOT")
	if root == "" {
		root = "/app/environment"
	}
	cycle := 1
	if v := os.Getenv("CYCLE"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cycle = n
		}
	}
	name := "catalog_view_a.json"
	if cycle > 1 {
		name = "catalog_view_b.json"
	}
	var cat store.CatFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", name), &cat); err != nil {
		fmt.Fprintf(os.Stderr, "viewctl: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("%s flags=%d finished=%v epoch=%d present_gen=%d\n",
		cat.LogicalPath, cat.StateFlags, cat.Finished, cat.Epoch, cat.PresentGen)
}
