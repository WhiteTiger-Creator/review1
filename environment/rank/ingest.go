package main

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type queryRow struct {
	Day      int
	Template string
}

func csvFiles(dir string) []string {
	entries, _ := os.ReadDir(dir)
	names := []string{}
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".csv") {
			names = append(names, filepath.Join(dir, e.Name()))
		}
	}
	sort.Strings(names)
	return names
}

func scanLines(path string, fn func(fields []string)) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	first := true
	for sc.Scan() {
		line := sc.Text()
		if first {
			first = false
			continue
		}
		if line == "" {
			continue
		}
		fn(strings.Split(line, ","))
	}
}

func readQueries(dir string) map[int]queryRow {
	out := map[int]queryRow{}
	scanLines(filepath.Join(dir, "queries.csv"), func(p []string) {
		if len(p) < 4 {
			return
		}
		q, _ := strconv.Atoi(p[0])
		d, _ := strconv.Atoi(p[1])
		out[q] = queryRow{Day: d, Template: p[2]}
	})
	return out
}

func readFeatures(dir string) (map[[2]int][]float64, int) {
	feats := map[[2]int][]float64{}
	nf := 0
	for _, path := range csvFiles(filepath.Join(dir, "features")) {
		f, err := os.Open(path)
		if err != nil {
			continue
		}
		sc := bufio.NewScanner(f)
		sc.Buffer(make([]byte, 1<<20), 1<<20)
		first := true
		for sc.Scan() {
			line := sc.Text()
			if first {
				first = false
				nf = len(strings.Split(line, ",")) - 2
				continue
			}
			if line == "" {
				continue
			}
			p := strings.Split(line, ",")
			q, _ := strconv.Atoi(p[0])
			d, _ := strconv.Atoi(p[1])
			v := make([]float64, nf)
			for k := 0; k < nf; k++ {
				v[k], _ = strconv.ParseFloat(p[2+k], 64)
			}
			feats[[2]int{q, d}] = v
		}
		f.Close()
	}
	return feats, nf
}

func readImpressions(dir string) []Impression {
	var out []Impression
	for _, path := range csvFiles(filepath.Join(dir, "impressions")) {
		scanLines(path, func(p []string) {
			if len(p) < 4 {
				return
			}
			q, _ := strconv.Atoi(p[0])
			rk, _ := strconv.Atoi(p[1])
			d, _ := strconv.Atoi(p[2])
			c, _ := strconv.Atoi(p[3])
			out = append(out, Impression{QueryID: q, SerpRank: rk, DocID: d, Clicked: c})
		})
	}
	return out
}

func readPageSlots(dir string) int {
	b, err := os.ReadFile(filepath.Join(dir, "serp_templates.json"))
	if err != nil {
		return 0
	}
	var cfg struct {
		PageSlots int `json:"page_slots"`
	}
	if json.Unmarshal(b, &cfg) != nil {
		return 0
	}
	return cfg.PageSlots
}
