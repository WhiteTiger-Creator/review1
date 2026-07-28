package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type row struct {
	feats []int
	label int
}

func readTables(dir string) map[string][]row {
	out := map[string][]row{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return out
	}
	names := []string{}
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".csv") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		data, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			continue
		}
		rows := []row{}
		for i, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if line == "" || i == 0 {
				continue
			}
			cells := strings.Split(line, ",")
			feats := []int{}
			for _, c := range cells[:len(cells)-1] {
				v, _ := strconv.Atoi(strings.TrimSpace(c))
				feats = append(feats, v)
			}
			label, _ := strconv.Atoi(strings.TrimSpace(cells[len(cells)-1]))
			rows = append(rows, row{feats: feats, label: label})
		}
		out[strings.TrimSuffix(name, ".csv")] = rows
	}
	return out
}

func report(tables map[string][]row, parts []string) []string {
	_ = tables
	_ = parts
	return nil
}

func main() {
	if len(os.Args) < 3 {
		os.Exit(1)
	}
	tables := readTables(os.Args[1])
	file, err := os.Open(os.Args[2])
	if err != nil {
		os.Exit(1)
	}
	defer file.Close()
	writer := bufio.NewWriter(os.Stdout)
	defer writer.Flush()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)
	for scanner.Scan() {
		parts := strings.Fields(scanner.Text())
		if len(parts) == 0 {
			continue
		}
		for _, l := range report(tables, parts) {
			fmt.Fprintln(writer, l)
		}
	}
}
