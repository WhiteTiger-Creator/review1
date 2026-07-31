package main

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type crown struct {
	name   string
	berths []string
	widths []int
	roll   []string
	seed   map[string]int
	record [][]string
}

func readRows(path string) [][]string {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	rows := [][]string{}
	for _, line := range strings.Split(string(raw), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		rows = append(rows, strings.Fields(trimmed))
	}
	return rows
}

func readCrown(root string) *crown {
	cr := &crown{seed: map[string]int{}}
	for _, row := range readRows(filepath.Join(root, "crown.conf")) {
		if row[0] == "name" && len(row) > 1 {
			cr.name = row[1]
		}
	}
	for _, row := range readRows(filepath.Join(root, "bracket.table")) {
		cr.berths = append(cr.berths, row[0])
	}
	for _, row := range readRows(filepath.Join(root, "widths.table")) {
		width, _ := strconv.Atoi(row[1])
		cr.widths = append(cr.widths, width)
	}
	for _, row := range readRows(filepath.Join(root, "roll.table")) {
		seed, _ := strconv.Atoi(row[1])
		cr.roll = append(cr.roll, row[0])
		cr.seed[row[0]] = seed
	}
	for _, row := range readRows(filepath.Join(root, "record", "crown.log")) {
		cr.record = append(cr.record, row[1:])
	}
	return cr
}
