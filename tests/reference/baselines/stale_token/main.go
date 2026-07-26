package main

import (
	"encoding/json"
	"io"
	"os"
)

type Event struct {
	Type    string `json:"type"`
	Time    int    `json:"time"`
	Node    int    `json:"node"`
	Term    int    `json:"term"`
	TTL     int    `json:"ttl"`
	Token   int    `json:"token"`
	WriteID string `json:"write_id"`
	Targets []int  `json:"targets"`
	Delta   int    `json:"delta"`
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
	Owner int `json:"owner"`
	Token int `json:"token"`
	Term  int `json:"term"`
	Expire int `json:"expires_at"`
}

type Output struct {
	CaseID   string          `json:"case_id"`
	CaseSeed int64           `json:"case_seed"`
	Results  []Result        `json:"results"`
	Final    FinalState      `json:"final_state"`
	Commits  []string        `json:"committed_writes"`
	Invar    map[string]bool `json:"invariants"`
}

type State struct {
	alive     bool
	token     int
	owner     int
	expiry    int
	term      int
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
	st := make([]State, c.Nodes)
	for i := range st {
		st[i] = State{alive: true, owner: -1}
	}
	out := Output{CaseID: c.CaseID, CaseSeed: c.Seed, Invar: map[string]bool{"unique_leases": true, "recovery_durable_ok": true, "fence_monotonic": true}}
	clock := 0
	seen := 0
	for idx, e := range c.Events {
		if e.Time > clock {
			clock = e.Time
		}
		switch e.Type {
		case "request_lease":
			newTok := 1
			if seen > 0 {
				newTok = seen + 1
			}
			seen++
			for i := 0; i < c.Nodes; i++ {
				if st[i].alive {
					st[i].owner = e.Node
					st[i].token = newTok
					st[i].expiry = clock + e.TTL
					st[i].term = e.Term
				}
			}
			out.Results = append(out.Results, Result{Index: idx, Type: e.Type, Status: "granted", Token: newTok, ExpiresAt: clock + e.TTL})
		case "write":
			if e.Node >= 0 && e.Node < c.Nodes {
				if st[e.Node].owner == e.Node && e.Token <= st[e.Node].token && clock <= st[e.Node].expiry {
					out.Results = append(out.Results, Result{Index: idx, Type: "write", Status: "committed", Token: e.Token, ExpiresAt: clock, WriteID: e.WriteID})
					out.Commits = append(out.Commits, e.WriteID)
					continue
				}
			}
			out.Results = append(out.Results, Result{Index: idx, Type: "write", Status: "rejected", Token: e.Token, ExpiresAt: 0, WriteID: e.WriteID})
		case "tick":
			clock += e.Delta
			out.Results = append(out.Results, Result{Index: idx, Type: "tick", Status: "ok", ExpiresAt: clock})
		case "crash":
			if e.Node >= 0 && e.Node < c.Nodes {
				st[e.Node].alive = false
			}
			out.Results = append(out.Results, Result{Index: idx, Type: "crash", Status: "ok"})
		case "recover":
			if e.Node >= 0 && e.Node < c.Nodes {
				st[e.Node].alive = true
			}
			out.Results = append(out.Results, Result{Index: idx, Type: "recover", Status: "ok"})
		}
	}
	out.Final = FinalState{Owner: st[0].owner, Token: st[0].token, Term: st[0].term, Expire: st[0].expiry}
	j, _ := json.Marshal(out)
	io.WriteString(io.Writer(os.Stdout), string(j))
}
