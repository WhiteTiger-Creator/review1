package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type tileJSON struct {
	Sq    []int   `json:"sq"`
	Paths [][]int `json:"paths"`
}

type tokenJSON struct {
	Cell []int `json:"cell"`
	P    int   `json:"p"`
}

type instance struct {
	N      int         `json:"n"`
	Board  []tileJSON  `json:"board"`
	Tokens []tokenJSON `json:"tokens"`
	Active int         `json:"active"`
	Tile   [][]int     `json:"tile"`
}

func gpoint(c, r, p int) [4]int {
	switch p {
	case 0:
		return [4]int{0, c, r, 0}
	case 1:
		return [4]int{0, c, r, 1}
	case 2:
		return [4]int{1, c, r, 1}
	case 3:
		return [4]int{1, c, r, 0}
	case 4:
		return [4]int{0, c, r - 1, 1}
	case 5:
		return [4]int{0, c, r - 1, 0}
	case 6:
		return [4]int{1, c - 1, r, 0}
	default:
		return [4]int{1, c - 1, r, 1}
	}
}

func cross(c, r, q int) (int, int, int) {
	switch q {
	case 0:
		return c, r + 1, 5
	case 1:
		return c, r + 1, 4
	case 2:
		return c + 1, r, 7
	case 3:
		return c + 1, r, 6
	case 4:
		return c, r - 1, 1
	case 5:
		return c, r - 1, 0
	case 6:
		return c - 1, r, 3
	default:
		return c - 1, r, 2
	}
}

func inBoard(n, c, r int) bool {
	return c >= 0 && c < n && r >= 0 && r < n
}

func mateOf(paths [][]int) (map[int]int, bool) {
	mate := map[int]int{}
	seen := map[int]bool{}
	for _, pr := range paths {
		if len(pr) != 2 {
			return nil, false
		}
		a, b := pr[0], pr[1]
		if a < 0 || a > 7 || b < 0 || b > 7 || a == b {
			return nil, false
		}
		if seen[a] || seen[b] {
			return nil, false
		}
		seen[a] = true
		seen[b] = true
		mate[a] = b
		mate[b] = a
	}
	if len(seen) != 8 {
		return nil, false
	}
	return mate, true
}

func walk(n int, tiles map[[2]int]map[int]int, c0, r0, p0 int) ([][4]int, string, [3]int) {
	trace := [][4]int{gpoint(c0, r0, p0)}
	c, r, p := c0, r0, p0
	if !inBoard(n, c, r) {
		return trace, "out", [3]int{}
	}
	mate, ok := tiles[[2]int{c, r}]
	if !ok {
		return trace, "stop", [3]int{c, r, p}
	}
	q := mate[p]
	c, r, p = cross(c, r, q)
	trace = append(trace, gpoint(c, r, p))
	if !inBoard(n, c, r) {
		return trace, "out", [3]int{}
	}
	return trace, "stop", [3]int{c, r, p}
}

func evaluate(line string) string {
	var in instance
	if err := json.Unmarshal([]byte(line), &in); err != nil {
		return "ERROR"
	}
	n := in.N
	tiles := map[[2]int]map[int]int{}
	for _, t := range in.Board {
		m, ok := mateOf(t.Paths)
		if !ok {
			return "ILLEGAL"
		}
		tiles[[2]int{t.Sq[0], t.Sq[1]}] = m
	}
	tokens := make([][3]int, len(in.Tokens))
	for i, tk := range in.Tokens {
		tokens[i] = [3]int{tk.Cell[0], tk.Cell[1], tk.P}
	}
	if in.Active < 0 || in.Active >= len(tokens) {
		return "ILLEGAL"
	}
	pm, ok := mateOf(in.Tile)
	if !ok {
		return "ILLEGAL"
	}
	placed := [2]int{tokens[in.Active][0], tokens[in.Active][1]}
	tiles[placed] = pm
	isMover := make([]bool, len(tokens))
	occ := make([]map[[4]int]bool, len(tokens))
	kind := make([]string, len(tokens))
	final := make([][3]int, len(tokens))
	for i := range tokens {
		c, r, p := tokens[i][0], tokens[i][1], tokens[i][2]
		if c == placed[0] && r == placed[1] {
			isMover[i] = true
			trace, k, f := walk(n, tiles, c, r, p)
			set := map[[4]int]bool{}
			for _, g := range trace {
				set[g] = true
			}
			occ[i] = set
			kind[i] = k
			final[i] = f
		} else {
			occ[i] = map[[4]int]bool{gpoint(c, r, p): true}
			kind[i] = "stay"
			final[i] = [3]int{c, r, p}
		}
	}
	counts := map[[4]int]int{}
	for i := range tokens {
		for g := range occ[i] {
			counts[g]++
		}
	}
	parts := make([]string, len(tokens))
	for i := range tokens {
		hit := false
		for g := range occ[i] {
			if counts[g] >= 2 {
				hit = true
				break
			}
		}
		if kind[i] == "out" || hit {
			parts[i] = fmt.Sprintf("%d:out", i)
		} else {
			f := final[i]
			parts[i] = fmt.Sprintf("%d:%d.%d.%d", i, f[0], f[1], f[2])
		}
	}
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("TOKENS %d", len(tokens)))
	for _, p := range parts {
		sb.WriteString(" ")
		sb.WriteString(p)
	}
	return sb.String()
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
