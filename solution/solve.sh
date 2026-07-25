#!/bin/bash
set -euo pipefail

cd /app

cat > /app/src/parser.go <<'GOEOF'
package main

import "fmt"

type Node interface{}

type Lit struct{ Ch byte }
type AnyChar struct{}
type BracketItem struct{ Lo, Hi byte }
type Bracket struct {
	Negate bool
	Items  []BracketItem
}
type Concat struct{ Parts []Node }
type Alt struct{ Branches []Node }
type Group struct {
	Idx   int
	Child Node
}
type Repeat struct {
	Child Node
	Lo    int
	Hi    int // -1 means unbounded
}
type AnchorStart struct{}
type AnchorEnd struct{}

type ParseError struct{ Msg string }

func (e *ParseError) Error() string { return e.Msg }

type Parser struct {
	p          string
	i          int
	n          int
	groupCount int
}

func NewParser(pattern string) *Parser {
	return &Parser{p: pattern, n: len(pattern)}
}

func (p *Parser) peek() (byte, bool) {
	if p.i < p.n {
		return p.p[p.i], true
	}
	return 0, false
}

func (p *Parser) Parse() (Node, int, error) {
	node, err := p.parseAlt()
	if err != nil {
		return nil, 0, err
	}
	if p.i != p.n {
		return nil, 0, &ParseError{fmt.Sprintf("unexpected char at %d", p.i)}
	}
	return node, p.groupCount, nil
}

func (p *Parser) parseAlt() (Node, error) {
	first, err := p.parseConcat()
	if err != nil {
		return nil, err
	}
	branches := []Node{first}
	for {
		c, ok := p.peek()
		if !ok || c != '|' {
			break
		}
		p.i++
		nxt, err := p.parseConcat()
		if err != nil {
			return nil, err
		}
		branches = append(branches, nxt)
	}
	if len(branches) == 1 {
		return branches[0], nil
	}
	return &Alt{Branches: branches}, nil
}

func (p *Parser) parseConcat() (Node, error) {
	var parts []Node
	for {
		c, ok := p.peek()
		if !ok || c == '|' || c == ')' {
			break
		}
		part, err := p.parseRepeat()
		if err != nil {
			return nil, err
		}
		parts = append(parts, part)
	}
	if len(parts) == 1 {
		return parts[0], nil
	}
	return &Concat{Parts: parts}, nil
}

func (p *Parser) looksLikeInterval() bool {
	j := p.i + 1
	sawDigit := false
	for j < p.n && p.p[j] >= '0' && p.p[j] <= '9' {
		sawDigit = true
		j++
	}
	if j < p.n && p.p[j] == ',' {
		j++
		for j < p.n && p.p[j] >= '0' && p.p[j] <= '9' {
			j++
		}
	}
	return sawDigit && j < p.n && p.p[j] == '}'
}

func (p *Parser) parseInterval() (int, int) {
	// assumes p.p[p.i] == '{'
	p.i++
	start := p.i
	for p.p[p.i] >= '0' && p.p[p.i] <= '9' {
		p.i++
	}
	lo := atoi(p.p[start:p.i])
	hi := lo
	if c, ok := p.peek(); ok && c == ',' {
		p.i++
		start2 := p.i
		for p.i < p.n && p.p[p.i] >= '0' && p.p[p.i] <= '9' {
			p.i++
		}
		if p.i > start2 {
			hi = atoi(p.p[start2:p.i])
		} else {
			hi = -1
		}
	}
	p.i++ // consume '}'
	return lo, hi
}

func atoi(s string) int {
	n := 0
	for i := 0; i < len(s); i++ {
		n = n*10 + int(s[i]-'0')
	}
	return n
}

func (p *Parser) parseRepeat() (Node, error) {
	atom, err := p.parseAtom()
	if err != nil {
		return nil, err
	}
	c, ok := p.peek()
	if !ok {
		return atom, nil
	}
	var result Node
	consumed := true
	switch {
	case c == '*':
		p.i++
		result = &Repeat{Child: atom, Lo: 0, Hi: -1}
	case c == '+':
		p.i++
		result = &Repeat{Child: atom, Lo: 1, Hi: -1}
	case c == '?':
		p.i++
		result = &Repeat{Child: atom, Lo: 0, Hi: 1}
	case c == '{' && p.looksLikeInterval():
		lo, hi := p.parseInterval()
		result = &Repeat{Child: atom, Lo: lo, Hi: hi}
	default:
		consumed = false
	}
	if !consumed {
		return atom, nil
	}
	// Reject a stacked second duplication symbol directly on the same atom:
	// undefined by POSIX ERE without an intervening group.
	if c2, ok := p.peek(); ok {
		if c2 == '*' || c2 == '+' || c2 == '?' || (c2 == '{' && p.looksLikeInterval()) {
			return nil, &ParseError{fmt.Sprintf("stacked duplication symbol at %d is undefined by POSIX ERE", p.i)}
		}
	}
	return result, nil
}

func (p *Parser) parseAtom() (Node, error) {
	c, ok := p.peek()
	if !ok {
		return nil, &ParseError{"unexpected end of pattern"}
	}
	switch c {
	case '(':
		p.i++
		p.groupCount++
		idx := p.groupCount
		child, err := p.parseAlt()
		if err != nil {
			return nil, err
		}
		if c2, ok := p.peek(); !ok || c2 != ')' {
			return nil, &ParseError{"missing )"}
		}
		p.i++
		return &Group{Idx: idx, Child: child}, nil
	case '^':
		p.i++
		return &AnchorStart{}, nil
	case '$':
		p.i++
		return &AnchorEnd{}, nil
	case '.':
		p.i++
		return &AnyChar{}, nil
	case '[':
		return p.parseBracket()
	case '\\':
		p.i++
		nc, ok := p.peek()
		if !ok {
			return nil, &ParseError{"dangling backslash"}
		}
		p.i++
		return &Lit{Ch: nc}, nil
	case '*', '+', '?':
		return nil, &ParseError{fmt.Sprintf("nothing to repeat at %d", p.i)}
	}
	p.i++
	return &Lit{Ch: c}, nil
}

func (p *Parser) parseBracket() (Node, error) {
	// assumes p.p[p.i] == '['
	p.i++
	negate := false
	if c, ok := p.peek(); ok && c == '^' {
		negate = true
		p.i++
	}
	var items []BracketItem
	first := true
	for {
		c, ok := p.peek()
		if !ok {
			return nil, &ParseError{"unterminated bracket expression"}
		}
		if c == ']' && !first {
			p.i++
			break
		}
		first = false
		var lo byte
		if c == ']' {
			p.i++
			lo = ']'
		} else {
			p.i++
			lo = c
		}
		if c2, ok := p.peek(); ok && c2 == '-' && p.i+1 < p.n && p.p[p.i+1] != ']' {
			p.i++
			hi, _ := p.peek()
			p.i++
			if lo > hi {
				return nil, &ParseError{fmt.Sprintf("reversed bracket range %c-%c: start collates after end", lo, hi)}
			}
			items = append(items, BracketItem{Lo: lo, Hi: hi})
		} else {
			items = append(items, BracketItem{Lo: lo, Hi: lo})
		}
	}
	return &Bracket{Negate: negate, Items: items}, nil
}
GOEOF

cat > /app/src/match.go <<'GOEOF'
package main

type reachKey struct {
	node Node
	pos  int
}

type Span struct {
	Start, End int
	Set        bool
}

func bracketMatches(b *Bracket, c byte) bool {
	inside := false
	for _, it := range b.Items {
		if it.Lo <= c && c <= it.Hi {
			inside = true
			break
		}
	}
	if b.Negate {
		return !inside
	}
	return inside
}

// reachable returns the set of end positions node can reach starting at i,
// against subject s, memoized on (node, i).
func reachable(node Node, i int, s string, memo map[reachKey]map[int]bool) map[int]bool {
	key := reachKey{node, i}
	if v, ok := memo[key]; ok {
		return v
	}
	memo[key] = map[int]bool{} // break cycles defensively
	result := reachableUncached(node, i, s, memo)
	memo[key] = result
	return result
}

func reachableUncached(node Node, i int, s string, memo map[reachKey]map[int]bool) map[int]bool {
	n := len(s)
	switch nd := node.(type) {
	case *Lit:
		if i < n && s[i] == nd.Ch {
			return map[int]bool{i + 1: true}
		}
		return map[int]bool{}
	case *AnyChar:
		if i < n {
			return map[int]bool{i + 1: true}
		}
		return map[int]bool{}
	case *Bracket:
		if i < n && bracketMatches(nd, s[i]) {
			return map[int]bool{i + 1: true}
		}
		return map[int]bool{}
	case *AnchorStart:
		if i == 0 {
			return map[int]bool{i: true}
		}
		return map[int]bool{}
	case *AnchorEnd:
		if i == n {
			return map[int]bool{i: true}
		}
		return map[int]bool{}
	case *Group:
		return reachable(nd.Child, i, s, memo)
	case *Alt:
		out := map[int]bool{}
		for _, b := range nd.Branches {
			for k := range reachable(b, i, s, memo) {
				out[k] = true
			}
		}
		return out
	case *Concat:
		frontier := map[int]bool{i: true}
		for _, part := range nd.Parts {
			nxt := map[int]bool{}
			for j := range frontier {
				for k := range reachable(part, j, s, memo) {
					nxt[k] = true
				}
			}
			frontier = nxt
			if len(frontier) == 0 {
				break
			}
		}
		return frontier
	case *Repeat:
		lo, hi := nd.Lo, nd.Hi
		cap := hi
		if hi == -1 {
			cap = n + 1
		}
		allEnds := map[int]bool{}
		if lo == 0 {
			allEnds[i] = true
		}
		frontier := map[int]bool{i: true}
		k := 0
		for k < cap {
			nxt := map[int]bool{}
			for j := range frontier {
				for e := range reachable(nd.Child, j, s, memo) {
					nxt[e] = true
				}
			}
			k++
			if len(nxt) == 0 {
				break
			}
			if k >= lo {
				for e := range nxt {
					allEnds[e] = true
				}
			}
			if setsEqual(nxt, frontier) && k >= lo {
				break
			}
			frontier = nxt
		}
		return allEnds
	}
	panic("unknown node type")
}

func setsEqual(a, b map[int]bool) bool {
	if len(a) != len(b) {
		return false
	}
	for k := range a {
		if !b[k] {
			return false
		}
	}
	return true
}

// FindOverallMatch returns the leftmost-longest (start, end) span, or ok=false.
func FindOverallMatch(node Node, s string) (start, end int, ok bool) {
	memo := map[reachKey]map[int]bool{}
	for st := 0; st <= len(s); st++ {
		ends := reachable(node, st, s, memo)
		if len(ends) > 0 {
			mx := -1
			for e := range ends {
				if e > mx {
					mx = e
				}
			}
			return st, mx, true
		}
	}
	return 0, 0, false
}

// ReconstructGroups performs the constrained backtracking parse described in
// the task documentation: given the fixed overall (start, end) span, prefer
// earlier-listed alternatives and maximal (greedy) repetition counts,
// backtracking only as needed to consume exactly [start, end).
func ReconstructGroups(node Node, ngroups int, s string, start, end int) ([]Span, bool) {
	groups := make([]Span, ngroups+1) // 1-indexed

	var m func(nd Node, i int, cont func(int) bool) bool
	m = func(nd Node, i int, cont func(int) bool) bool {
		switch v := nd.(type) {
		case *Lit:
			if i < end && s[i] == v.Ch {
				return cont(i + 1)
			}
			return false
		case *AnyChar:
			if i < end {
				return cont(i + 1)
			}
			return false
		case *Bracket:
			if i < end && bracketMatches(v, s[i]) {
				return cont(i + 1)
			}
			return false
		case *AnchorStart:
			if i == 0 {
				return cont(i)
			}
			return false
		case *AnchorEnd:
			if i == len(s) {
				return cont(i)
			}
			return false
		case *Group:
			saved := groups[v.Idx]
			wrapped := func(j int) bool {
				groups[v.Idx] = Span{i, j, true}
				if cont(j) {
					return true
				}
				groups[v.Idx] = saved
				return false
			}
			ok := m(v.Child, i, wrapped)
			if !ok {
				groups[v.Idx] = saved
			}
			return ok
		case *Alt:
			for _, b := range v.Branches {
				if m(b, i, cont) {
					return true
				}
			}
			return false
		case *Concat:
			var build func(idx int) func(int) bool
			build = func(idx int) func(int) bool {
				if idx == len(v.Parts) {
					return cont
				}
				return func(j int) bool {
					return m(v.Parts[idx], j, build(idx+1))
				}
			}
			return build(0)(i)
		case *Repeat:
			if v.Hi != -1 {
				return matchBoundedRepeat(m, v.Child, i, v.Lo, v.Hi, cont)
			}
			return matchUnboundedRepeat(m, v, i, 0, cont)
		}
		panic("unknown node type")
	}

	ok := m(node, start, func(j int) bool { return j == end })
	return groups, ok
}

func matchBoundedRepeat(m func(Node, int, func(int) bool) bool, child Node, i, lo, hi int, cont func(int) bool) bool {
	var mandatory func(i, remaining int, cont func(int) bool) bool
	var optional func(i, remaining int, cont func(int) bool) bool
	mandatory = func(i, remaining int, cont func(int) bool) bool {
		if remaining == 0 {
			return optional(i, hi-lo, cont)
		}
		return m(child, i, func(j int) bool { return mandatory(j, remaining-1, cont) })
	}
	optional = func(i, remaining int, cont func(int) bool) bool {
		if remaining == 0 {
			return cont(i)
		}
		take := func(j int) bool { return optional(j, remaining-1, cont) }
		if m(child, i, take) {
			return true
		}
		return cont(i)
	}
	return mandatory(i, lo, cont)
}

func matchUnboundedRepeat(m func(Node, int, func(int) bool) bool, nd *Repeat, i, count int, cont func(int) bool) bool {
	lo := nd.Lo
	if count < lo {
		return m(nd.Child, i, func(j int) bool {
			return matchUnboundedRepeat(m, nd, j, count+1, cont)
		})
	}
	after := func(j int) bool {
		if j == i {
			if count == 0 {
				return cont(i)
			}
			return false
		}
		return matchUnboundedRepeat(m, nd, j, count+1, cont)
	}
	if m(nd.Child, i, after) {
		return true
	}
	return cont(i)
}
GOEOF

cat > /app/src/main.go <<'GOEOF'
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
	pattern := os.Args[1]
	subject := os.Args[2]

	parser := NewParser(pattern)
	node, ngroups, err := parser.Parse()
	if err != nil {
		fmt.Println("PARSE_ERROR")
		os.Exit(1)
	}

	start, end, ok := FindOverallMatch(node, subject)
	if !ok {
		fmt.Println("NOMATCH")
		os.Exit(0)
	}
	groups, recOk := ReconstructGroups(node, ngroups, subject, start, end)
	if !recOk {
		fmt.Println("NOMATCH")
		os.Exit(0)
	}
	fmt.Printf("MATCH %d %d\n", start, end)
	for idx := 1; idx <= ngroups; idx++ {
		sp := groups[idx]
		if sp.Set {
			fmt.Printf("GROUP %d %d %d\n", idx, sp.Start, sp.End)
		} else {
			fmt.Printf("GROUP %d NOMATCH\n", idx)
		}
	}
	os.Exit(0)
}
GOEOF

go build -o /app/posixmatch ./src

if [ ! -x /app/posixmatch ]; then
    echo "build smoke failed: binary missing" >&2
    exit 1
fi

OUT=$(/app/posixmatch '(a|ab)(c|bcd)(d*)' 'abcd')
EXPECTED=$'MATCH 0 4\nGROUP 1 0 1\nGROUP 2 1 4\nGROUP 3 4 4'
if [ "$OUT" != "$EXPECTED" ]; then
    echo "build smoke failed: unexpected output for sample case, got: $OUT" >&2
    exit 1
fi
