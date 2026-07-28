package main

import (
	"bufio"
	"fmt"
	"math/big"
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

func pairScore(rows []row, a, b, card, classes int) *big.Rat {
	total := new(big.Rat)
	for c := 0; c < classes; c++ {
		block := []row{}
		for _, r := range rows {
			if r.label == c {
				block = append(block, r)
			}
		}
		n := len(block)
		if n == 0 {
			continue
		}
		joint := map[[2]int]int64{}
		left := map[int]int64{}
		right := map[int]int64{}
		for _, r := range block {
			joint[[2]int{r.feats[a], r.feats[b]}]++
			left[r.feats[a]]++
			right[r.feats[b]]++
		}
		for u := 0; u < card; u++ {
			for v := 0; v < card; v++ {
				expected := new(big.Rat).SetFrac64(left[u]*right[v], int64(n))
				if expected.Sign() == 0 {
					continue
				}
				observed := new(big.Rat).SetInt64(joint[[2]int{u, v}])
				delta := new(big.Rat).Sub(observed, expected)
				term := new(big.Rat).Mul(delta, delta)
				term.Quo(term, expected)
				total.Add(total, term)
			}
		}
	}
	return total
}

type edge struct {
	score *big.Rat
	a     int
	b     int
}

func spanning(features int, scores map[[2]int]*big.Rat) []edge {
	edges := []edge{}
	for a := 0; a < features; a++ {
		for b := a + 1; b < features; b++ {
			edges = append(edges, edge{score: scores[[2]int{a, b}], a: a, b: b})
		}
	}
	sort.SliceStable(edges, func(i, j int) bool {
		c := edges[i].score.Cmp(edges[j].score)
		if c != 0 {
			return c > 0
		}
		if edges[i].a != edges[j].a {
			return edges[i].a < edges[j].a
		}
		return edges[i].b < edges[j].b
	})
	parent := make([]int, features)
	for i := range parent {
		parent[i] = i
	}
	var find func(int) int
	find = func(x int) int {
		for parent[x] != x {
			parent[x] = parent[parent[x]]
			x = parent[x]
		}
		return x
	}
	chosen := []edge{}
	for _, e := range edges {
		ra, rb := find(e.a), find(e.b)
		if ra == rb {
			continue
		}
		parent[ra] = rb
		chosen = append(chosen, e)
	}
	return chosen
}

func orient(features int, chosen []edge) []int {
	adjacency := map[int][]int{}
	for _, e := range chosen {
		adjacency[e.a] = append(adjacency[e.a], e.b)
		adjacency[e.b] = append(adjacency[e.b], e.a)
	}
	parent := make([]int, features)
	for i := range parent {
		parent[i] = -1
	}
	seen := map[int]bool{0: true}
	stack := []int{0}
	for len(stack) > 0 {
		node := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		next := append([]int{}, adjacency[node]...)
		sort.Ints(next)
		for _, nx := range next {
			if !seen[nx] {
				seen[nx] = true
				parent[nx] = node
				stack = append(stack, nx)
			}
		}
	}
	return parent
}

func predict(rows []row, parent []int, card, classes int, feats []int) (int, *big.Rat) {
	best := 0
	var bestScore *big.Rat
	n := int64(len(rows))
	for c := 0; c < classes; c++ {
		var count int64
		for _, r := range rows {
			if r.label == c {
				count++
			}
		}
		score := new(big.Rat).SetFrac64(count+1, n+int64(classes))
		for j := 0; j < len(feats); j++ {
			p := parent[j]
			var numer, denom int64
			for _, r := range rows {
				if r.label != c {
					continue
				}
				if p < 0 {
					denom++
					if r.feats[j] == feats[j] {
						numer++
					}
				} else if r.feats[p] == feats[p] {
					denom++
					if r.feats[j] == feats[j] {
						numer++
					}
				}
			}
			score.Mul(score, new(big.Rat).SetFrac64(numer+1, denom+int64(card)))
		}
		if bestScore == nil || score.Cmp(bestScore) > 0 {
			bestScore = score
			best = c
		}
	}
	return best, bestScore
}

func render(v *big.Rat) string {
	return v.Num().String() + "/" + v.Denom().String()
}

func handle(tables map[string][]row, parts []string) ([]string, bool) {
	if len(parts) != 3 {
		return nil, false
	}
	rows, ok := tables[parts[1]]
	if !ok {
		return nil, false
	}
	probes, ok := tables[parts[2]]
	if !ok {
		return nil, false
	}
	if len(rows) < 2 || len(probes) == 0 {
		return nil, false
	}
	features := len(rows[0].feats)
	if features < 2 {
		return nil, false
	}
	for _, r := range rows {
		if len(r.feats) != features {
			return nil, false
		}
	}
	for _, p := range probes {
		if len(p.feats) != features {
			return nil, false
		}
	}
	seen := map[int]bool{}
	maxLabel, card := 0, 0
	for _, r := range rows {
		seen[r.label] = true
		if r.label > maxLabel {
			maxLabel = r.label
		}
		for _, f := range r.feats {
			if f > card {
				card = f
			}
		}
	}
	if len(seen) < 2 {
		return nil, false
	}
	classes := maxLabel + 1
	card++
	scores := map[[2]int]*big.Rat{}
	for a := 0; a < features; a++ {
		for b := a + 1; b < features; b++ {
			scores[[2]int{a, b}] = pairScore(rows, a, b, card, classes)
		}
	}
	chosen := spanning(features, scores)
	parent := orient(features, chosen)
	qid := parts[0]
	lines := []string{}
	ordered := append([]edge{}, chosen...)
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].a != ordered[j].a {
			return ordered[i].a < ordered[j].a
		}
		return ordered[i].b < ordered[j].b
	})
	for _, e := range ordered {
		lines = append(lines, fmt.Sprintf("%s E %d %d S %s", qid, e.a, e.b, render(e.score)))
	}
	tree := []string{}
	for _, p := range parent {
		tree = append(tree, strconv.Itoa(p))
	}
	lines = append(lines, fmt.Sprintf("%s T %s", qid, strings.Join(tree, " ")))
	for i, p := range probes {
		c, score := predict(rows, parent, card, classes, p.feats)
		lines = append(lines, fmt.Sprintf("%s P %d C %d W %s", qid, i, c, render(score)))
	}
	return lines, true
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
		lines, ok := handle(tables, parts)
		if !ok {
			fmt.Fprintf(writer, "%s REJECT\n", parts[0])
			continue
		}
		for _, l := range lines {
			fmt.Fprintln(writer, l)
		}
	}
}
