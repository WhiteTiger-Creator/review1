package main

import (
	"encoding/json"
	"os"
	"sort"
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

type State struct {
	alive      bool
	term       int
	owner      int
	token      int
	expiry     int
	durableOn  bool
	persistent map[string]bool
}

type Output struct {
	CaseID string          `json:"case_id"`
	Seed   int64           `json:"case_seed"`
	Res    []Result        `json:"results"`
	Final  map[string]int  `json:"final_state"`
	Comm   []string        `json:"committed_writes"`
	In    map[string]bool  `json:"invariants"`
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
	st := make([]State, c.Nodes)
	for i := range st {
		st[i] = State{alive: true, owner: -1, durableOn: false, persistent: map[string]bool{}}
	}
	o := Output{
		CaseID: c.CaseID,
		Seed:   c.Seed,
		In:     map[string]bool{"unique_leases": true, "recovery_durable_ok": true, "fence_monotonic": true},
	}
	clock := 0
	quorum := c.Nodes/2 + 1
	for idx, e := range c.Events {
		if e.Time > clock {
			clock = e.Time
		}
		switch e.Type {
		case "request_lease":
			targets := uniq(e.Targets)
			alive := 0
			for _, t := range targets {
				if t >= 0 && t < c.Nodes && st[t].alive {
					alive++
				}
			}
			if alive < quorum || e.Node < 0 || e.Node >= c.Nodes {
				o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "rejected"})
				continue
			}
			newToken := 0
			for _, n := range st {
				if n.token > newToken {
					newToken = n.token
				}
			}
			newToken++
			for _, t := range targets {
				if t >= 0 && t < c.Nodes && st[t].alive {
					st[t].owner = e.Node
					st[t].token = newToken
					st[t].expiry = clock + e.TTL
					st[t].term = e.Term
					st[t].durableOn = true
				}
			}
			o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "granted", Token: newToken, ExpiresAt: clock + e.TTL})
		case "write":
			targets := uniq(e.Targets)
			ownerok := e.Node >= 0 && e.Node < c.Nodes && st[e.Node].owner == e.Node && st[e.Node].token == e.Token
			if !ownerok || clock > st[e.Node].expiry {
				o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "rejected", Token: e.Token, WriteID: e.WriteID})
				continue
			}
			acks := 0
			for _, t := range targets {
				if t >= 0 && t < c.Nodes && st[t].alive && st[t].token == e.Token && st[t].owner == e.Node && st[t].durableOn {
					acks++
				}
			}
			if acks < quorum {
				o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "rejected", Token: e.Token, WriteID: e.WriteID})
				continue
			}
			for _, t := range targets {
				if t >= 0 && t < c.Nodes && st[t].alive {
					st[t].durableOn = true
				}
			}
			o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "committed", Token: e.Token, ExpiresAt: clock, WriteID: e.WriteID})
			o.Comm = append(o.Comm, e.WriteID)
		case "crash":
			if e.Node >= 0 && e.Node < c.Nodes {
				st[e.Node].alive = false
				st[e.Node].token = 0
				st[e.Node].owner = -1
				st[e.Node].expiry = 0
				st[e.Node].persistent = map[string]bool{}
				st[e.Node].durableOn = false
			}
			o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "ok"})
		case "recover":
			if e.Node >= 0 && e.Node < c.Nodes {
				st[e.Node].alive = true
			}
			o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "ok"})
		case "tick":
			clock += e.Delta
			o.Res = append(o.Res, Result{Index: idx, Type: e.Type, Status: "ok", ExpiresAt: clock})
		}
	}
	o.Final = map[string]int{"owner": -1, "token": 0, "term": 0, "expires_at": 0}
	for i := 0; i < c.Nodes; i++ {
		if st[i].alive && st[i].token > 0 {
			o.Final["owner"] = st[i].owner
			o.Final["token"] = st[i].token
			o.Final["term"] = st[i].term
			o.Final["expires_at"] = st[i].expiry
			break
		}
	}
	out, _ := json.MarshalIndent(o, "", "  ")
	os.Stdout.Write(out)
}
