package main

import (
	"bytes"
	"flag"
	"fmt"
	"hxenv/lib/core"
	"hxenv/m9"
	"hxenv/n2"
	"hxenv/p6"
	"hxenv/w3"
	"os"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: gm_infer settle|recover|status|compact")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "settle":
		runPass(os.Args[2:])
	case "recover":
		runRepair(os.Args[2:])
	case "status":
		runView(os.Args[2:])
	case "compact":
		runSquash(os.Args[2:])
	default:
		os.Exit(2)
	}
}

func runPass(a []string) {
	f := flag.NewFlagSet("settle", flag.ExitOnError)
	g1 := f.String("g1", "", "")
	g2 := f.String("g2", "", "")
	ss := f.String("scraps", "", "")
	su := f.String("sum", "", "")
	ar := f.String("arms", "a7,b2", "")
	n := f.String("nest", "", "")
	v := f.String("var", "/app/environment/var", "")
	o := f.String("out", "/app/output/graph_probe.json", "")
	f.Parse(a)
	x := read(*g1)
	y := read(*g2)
	z := read(*su)
	var sc [][]byte
	var paths []string
	for _, q := range strings.Split(*ss, ",") {
		q = strings.TrimSpace(q)
		if q == "" {
			continue
		}
		sc = append(sc, read(q))
		paths = append(paths, q)
	}
	finger := core.Finger(x, y, z, sc, *ar)
	soft := bytes.Equal(x, y) || len(paths) < 2
	if !soft {
		if tip, ok, e := n2.Replay(*v); e == nil && ok && tip.Journal.Finger == finger && !tip.Journal.Soft {
			bail(p6.Lay(tip.Journal.Plan, *n))
			bail(p6.Probe(tip.Journal.Plan, *o))
			bail(n2.StripSoft(*v))
			return
		}
	}
	state, e := m9.Fold(x, y, z)
	bail(e)
	p, e := m9.Close(state, sc, z, *ar)
	bail(e)
	bail(p6.Lay(p, *n))
	bail(p6.Probe(p, *o))
	_, e = p6.Commit(*v, finger, *n, p, soft)
	bail(e)
}

func runRepair(a []string) {
	fs := flag.NewFlagSet("recover", flag.ExitOnError)
	n := fs.String("nest", "", "")
	v := fs.String("var", "/app/environment/var", "")
	o := fs.String("out", "/app/output/graph_probe.json", "")
	fs.Parse(a)
	bail(n2.RewriteValid(*v))
	s, ok, e := n2.Replay(*v)
	bail(e)
	if ok {
		bail(p6.Lay(s.Journal.Plan, *n))
		bail(p6.Probe(s.Journal.Plan, *o))
	}
}

func runView(a []string) {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	n := fs.String("nest", "", "")
	v := fs.String("var", "/app/environment/var", "")
	o := fs.String("out", "/app/output/graph_probe.json", "")
	fs.Parse(a)
	bail(w3.Status(*v, *n, *o))
}

func runSquash(a []string) {
	fs := flag.NewFlagSet("compact", flag.ExitOnError)
	v := fs.String("var", "/app/environment/var", "")
	fs.Parse(a)
	bail(n2.Squash(*v))
}

func read(p string) []byte {
	if p == "" {
		return nil
	}
	b, e := os.ReadFile(p)
	bail(e)
	return b
}

func bail(e error) {
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
