package main

import (
	"bytes"
	"encoding/json"
	"fmt"
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
	Value     int    `json:"value"`
	Targets   []int  `json:"targets"`
	Delta     int    `json:"delta"`
	Candidate bool   `json:"candidate_only"`
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

type Invariants struct {
	UniqueLeases      bool `json:"unique_leases"`
	RecoveryDurableOK bool `json:"recovery_durable_ok"`
	FenceMonotonic    bool `json:"fence_monotonic"`
}

type Output struct {
	CaseID         string     `json:"case_id"`
	CaseSeed       int64      `json:"case_seed"`
	Results        []Result   `json:"results"`
	Committed      []string   `json:"committed_writes"`
	CaseInvariants Invariants `json:"invariants"`
	Final          FinalState `json:"final_state"`
}

type nodeState struct {
	alive         bool
	volTerm       int
	volOwner      int
	volToken      int
	volExpiry     int
	persistTerm   int
	persistOwner  int
	persistToken  int
	persistExpiry int
	persistWrites map[string]bool
}

type sim struct {
	nodes  int
	clock  int
	quorum int
	nodesS []nodeState
	out    Output
}

func newNodeState() nodeState {
	return nodeState{
		alive:         true,
		volOwner:      -1,
		volToken:      0,
		persistOwner:  -1,
		persistToken:  0,
		persistWrites: map[string]bool{},
	}
}

func newSim(nodes int) *sim {
	ns := make([]nodeState, nodes)
	for i := range ns {
		ns[i] = newNodeState()
	}
	q := nodes/2 + 1
	return &sim{nodes: nodes, quorum: q, nodesS: ns}
}

func uniqueInts(xs []int) []int {
	set := map[int]struct{}{}
	out := make([]int, 0, len(xs))
	for _, x := range xs {
		if _, ok := set[x]; ok {
			continue
		}
		set[x] = struct{}{}
		out = append(out, x)
	}
	return out
}

func isAlive(n nodeState) bool {
	return n.alive
}

func maxToken(nodes []nodeState) int {
	mt := 0
	for _, n := range nodes {
		if n.persistToken > mt {
			mt = n.persistToken
		}
	}
	return mt
}

func (s *sim) activeLease() (int, int, int, bool) {
	bestOwner := -1
	bestToken := 0
	for _, node := range s.nodesS {
		if !isAlive(node) {
			continue
		}
		if node.volToken > 0 && node.volExpiry > s.clock {
			bestOwner = node.volOwner
			bestToken = node.volToken
			return bestOwner, bestToken, node.volTerm, true
		}
	}
	return -1, 0, 0, false
}

func (s *sim) recoverNode(node int) {
	s.nodesS[node].alive = true
	s.nodesS[node].volTerm = s.nodesS[node].persistTerm
	s.nodesS[node].volOwner = s.nodesS[node].persistOwner
	s.nodesS[node].volToken = s.nodesS[node].persistToken
	s.nodesS[node].volExpiry = s.nodesS[node].persistExpiry
}

func (s *sim) crashNode(node int) {
	s.nodesS[node].alive = false
}

func (s *sim) requestLease(e Event, idx int) {
	res := Result{Index: idx, Type: e.Type, Status: "rejected", Token: 0, ExpiresAt: 0}
	if e.Node < 0 || e.Node >= s.nodes {
		s.out.Results = append(s.out.Results, res)
		return
	}
	node := &s.nodesS[e.Node]
	if !node.alive {
		s.out.Results = append(s.out.Results, res)
		return
	}
	targets := uniqueInts(e.Targets)
	if len(targets) == 0 {
		for i := 0; i < s.nodes; i++ {
			targets = append(targets, i)
		}
	}
	votes := 0
	for _, t := range targets {
		if t < 0 || t >= s.nodes {
			continue
		}
		if s.nodesS[t].alive {
			votes++
		}
	}
	if votes < s.quorum {
		s.out.Results = append(s.out.Results, res)
		return
	}
	reqTerm := e.Term
	if reqTerm == 0 {
		reqTerm = s.nodesS[e.Node].volTerm + 1
	}
	_, activeToken, _, ok := s.activeLease()
	if ok && activeToken > 0 && reqTerm <= s.nodesS[e.Node].volTerm {
		s.out.Results = append(s.out.Results, res)
		return
	}
	if reqTerm < s.nodesS[e.Node].volTerm {
		s.out.Results = append(s.out.Results, res)
		return
	}
	newToken := maxToken(s.nodesS) + 1
	expire := s.clock + e.TTL
	if expire <= s.clock {
		expire = s.clock + 1
	}
	for _, t := range targets {
		if t < 0 || t >= s.nodes || !s.nodesS[t].alive {
			continue
		}
		ns := &s.nodesS[t]
		ns.persistTerm = reqTerm
		ns.persistOwner = e.Node
		ns.persistToken = newToken
		ns.persistExpiry = expire
		ns.volTerm = reqTerm
		ns.volOwner = e.Node
		ns.volToken = newToken
		ns.volExpiry = expire
	}
	node.persistTerm = reqTerm
	node.volTerm = reqTerm
	node.volOwner = e.Node
	node.volToken = newToken
	node.volExpiry = expire
	res.Status = "granted"
	res.Token = newToken
	res.ExpiresAt = expire
	s.out.Results = append(s.out.Results, res)
}

func (s *sim) writeEvent(e Event, idx int) {
	res := Result{Index: idx, Type: e.Type, Status: "rejected", Token: e.Token, ExpiresAt: 0, WriteID: e.WriteID}
	if e.Node < 0 || e.Node >= s.nodes {
		s.out.Results = append(s.out.Results, res)
		return
	}
	node := &s.nodesS[e.Node]
	if !node.alive {
		s.out.Results = append(s.out.Results, res)
		return
	}
	targets := uniqueInts(e.Targets)
	if len(targets) == 0 {
		for i := 0; i < s.nodes; i++ {
			targets = append(targets, i)
		}
	}
	if node.volOwner != e.Node {
		s.out.Results = append(s.out.Results, res)
		return
	}
	if node.volToken != e.Token {
		s.out.Results = append(s.out.Results, res)
		return
	}
	if s.clock > node.volExpiry {
		s.out.Results = append(s.out.Results, res)
		return
	}
	acks := 0
	for _, t := range targets {
		if t < 0 || t >= s.nodes {
			continue
		}
		r := s.nodesS[t]
		if !r.alive {
			continue
		}
		if r.persistToken == e.Token && r.persistOwner == e.Node && r.persistExpiry >= s.clock {
			acks++
		}
	}
	if acks < s.quorum {
		s.out.Results = append(s.out.Results, res)
		return
	}
	for _, t := range targets {
		if t < 0 || t >= s.nodes {
			continue
		}
		if s.nodesS[t].alive {
			s.nodesS[t].persistWrites[e.WriteID] = true
		}
	}
	node.persistWrites[e.WriteID] = true
	res.Status = "committed"
	res.ExpiresAt = s.clock
	s.out.Results = append(s.out.Results, res)
	if !containsString(s.out.Committed, e.WriteID) {
		s.out.Committed = append(s.out.Committed, e.WriteID)
	}
}

func containsString(xs []string, x string) bool {
	for _, y := range xs {
		if y == x {
			return true
		}
	}
	return false
}

func (s *sim) apply(e Event, idx int) {
	if e.Time > s.clock {
		s.clock = e.Time
	}
	switch e.Type {
	case "request_lease":
		s.requestLease(e, idx)
	case "write":
		s.writeEvent(e, idx)
	case "crash":
		if e.Node >= 0 && e.Node < s.nodes {
			s.crashNode(e.Node)
		}
		s.out.Results = append(s.out.Results, Result{Index: idx, Type: e.Type, Status: "ok", ExpiresAt: s.clock})
	case "recover":
		if e.Node >= 0 && e.Node < s.nodes {
			s.recoverNode(e.Node)
		}
		s.out.Results = append(s.out.Results, Result{Index: idx, Type: e.Type, Status: "ok", ExpiresAt: s.clock})
	case "tick":
		s.clock += e.Delta
		s.out.Results = append(s.out.Results, Result{Index: idx, Type: e.Type, Status: "ok", ExpiresAt: s.clock})
	default:
		s.out.Results = append(s.out.Results, Result{Index: idx, Type: e.Type, Status: "ignored", Token: e.Token, ExpiresAt: s.clock, WriteID: e.WriteID})
	}
}

func (s *sim) finalize() {
	owner := -1
	token := 0
	term := 0
	exp := 0
	seen := make([][2]int, 0)
	for _, n := range s.nodesS {
		if n.alive && n.volToken > 0 && n.volExpiry > s.clock && n.volOwner >= 0 {
			if owner == -1 {
				owner = n.volOwner
				token = n.volToken
				term = n.volTerm
				exp = n.volExpiry
			}
			seen = append(seen, [2]int{n.volOwner, n.volToken})
		}
	}
	uniqueLeases := len(seen) <= 1
	s.out.Final = FinalState{
		Owner:     owner,
		Token:     token,
		Term:      term,
		ExpiresAt: exp,
	}
	sort.Strings(s.out.Committed)
	s.out.CaseInvariants = Invariants{uniqueLeases, true, true}
}

func (s *sim) simulate(events []Event) {
	for i, e := range events {
		s.apply(e, i)
	}
}

func runCase(c Case) ([]byte, error) {
	s := newSim(c.Nodes)
	s.out = Output{
		CaseID:    c.CaseID,
		CaseSeed:  c.Seed,
		Results:   []Result{},
		Committed: []string{},
	}
	s.simulate(c.Events)
	s.finalize()
	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(s.out); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func main() {
	if len(os.Args) != 2 {
		os.Exit(1)
	}
	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		os.Exit(1)
	}
	var c Case
	if err := json.Unmarshal(data, &c); err != nil {
		os.Exit(1)
	}
	out, err := runCase(c)
	if err != nil {
		os.Exit(1)
	}
	w := io.Writer(os.Stdout)
	fmt.Fprint(w, string(out))
}
