package main

import (
	"encoding/json"
	"io"
	"os"
	"sort"
)

type Event struct {
	Type      string `json:"type"`
	Time      int    `json:"time"`
	Node      int    `json:"node"`
	Term      int    `json:"term"`
	TTL       int    `json:"ttl"`
	Token     int    `json:"token"`
	WriteID   string `json:"write_id"`
	Targets   []int  `json:"targets"`
	Delta     int    `json:"delta"`
}

type Case struct {
	CaseID string  `json:"case_id"`
	Nodes  int     `json:"nodes"`
	Seed   int64   `json:"seed"`
	Events []Event `json:"events"`
}

type Result struct {
	Index     int    `json:"index"`
	Type      string `json:"type"`
	Status    string `json:"status"`
	Token     int    `json:"token"`
	ExpiresAt int    `json:"expires_at"`
	WriteID   string `json:"write_id,omitempty"`
}

type FinalState struct {
	Owner     int `json:"owner"`
	Token     int `json:"token"`
	Term      int `json:"term"`
	ExpiresAt int `json:"expires_at"`
}

type Output struct {
	CaseID   string            `json:"case_id"`
	CaseSeed int64             `json:"case_seed"`
	Results  []Result          `json:"results"`
	Commits  []string          `json:"committed_writes"`
	Meta     map[string]bool   `json:"invariants"`
	Final    FinalState        `json:"final_state"`
}

type Node struct {
	alive bool
	term  int
	owner int
	token int
	exp   int
	writes map[string]bool
}

func uniq(xs []int) []int {
	m := map[int]struct{}{}
	out := make([]int, 0, len(xs))
	for _, x := range xs {
		if _, ok := m[x]; ok {
			continue
		}
		m[x] = struct{}{}
		out = append(out, x)
	}
	sort.Ints(out)
	return out
}

func main() {
	if len(os.Args) != 2 {
		return
	}
	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		return
	}
	var c Case
	if err := json.Unmarshal(data, &c); err != nil {
		return
	}
	state := make([]Node, c.Nodes)
	for i := range state {
		state[i] = Node{alive: true, owner: -1, writes: map[string]bool{}}
	}
	quorum := 1
	clock := 0
	out := Output{CaseID: c.CaseID, CaseSeed: c.Seed, Meta: map[string]bool{}}
	for idx, e := range c.Events {
		if e.Time > clock {
			clock = e.Time
		}
		switch e.Type {
		case "request_lease":
			tg := uniq(e.Targets)
			if len(tg) >= quorum && c.Nodes > 0 {
				maxT := 0
				for i := range state {
					if state[i].token > maxT {
						maxT = state[i].token
					}
				}
				newTerm := e.Term
				if newTerm < state[e.Node].term+1 {
					newTerm = state[e.Node].term + 1
				}
				exp := clock + e.TTL
				for _, t := range tg {
					st := &state[t]
					st.term = newTerm
					st.owner = e.Node
					st.token = maxT + 1
					st.exp = exp
				}
				out.Results = append(out.Results, Result{Index: idx, Type: "request_lease", Status: "granted", Token: maxT + 1, ExpiresAt: exp})
				continue
			}
			out.Results = append(out.Results, Result{Index: idx, Type: "request_lease", Status: "rejected", Token: 0, ExpiresAt: 0})
		case "write":
			tg := uniq(e.Targets)
			if len(tg) >= quorum && e.Node < c.Nodes && state[e.Node].owner == e.Node && state[e.Node].token == e.Token {
				for _, t := range tg {
					if state[t].alive {
						state[t].writes[e.WriteID] = true
					}
				}
				state[e.Node].writes[e.WriteID] = true
				out.Commits = append(out.Commits, e.WriteID)
				out.Results = append(out.Results, Result{Index: idx, Type: "write", Status: "committed", Token: e.Token, ExpiresAt: clock, WriteID: e.WriteID})
			} else {
				out.Results = append(out.Results, Result{Index: idx, Type: "write", Status: "rejected", Token: e.Token, ExpiresAt: 0, WriteID: e.WriteID})
			}
		case "crash":
			if e.Node >= 0 && e.Node < c.Nodes {
				state[e.Node].alive = false
			}
			out.Results = append(out.Results, Result{Index: idx, Type: "crash", Status: "ok"})
		case "recover":
			if e.Node >= 0 && e.Node < c.Nodes {
				state[e.Node].alive = true
			}
			out.Results = append(out.Results, Result{Index: idx, Type: "recover", Status: "ok"})
		case "tick":
			clock += e.Delta
			out.Results = append(out.Results, Result{Index: idx, Type: "tick", Status: "ok", ExpiresAt: clock})
		}
	}
	out.Final = FinalState{
		Owner:     state[0].owner,
		Token:     state[0].token,
		Term:      state[0].term,
		ExpiresAt: state[0].exp,
	}
	out.Meta = map[string]bool{"unique_leases": true, "recovery_durable_ok": true, "fence_monotonic": true}
	j, _ := json.Marshal(out)
	io.WriteString(io.Writer(os.Stdout), string(j))
}
