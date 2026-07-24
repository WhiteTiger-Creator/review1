package deck

import (
	"fmt"
	"os"
	"sort"
	"strings"
)

// BusType is the declared operating type.
type BusType string

const (
	BusSlack BusType = "SLACK"
	BusPV    BusType = "PV"
	BusPQ    BusType = "PQ"
)

// BusRecord is one BUS line.
type BusRecord struct {
	ID      string
	Type    BusType
	VSet    float64
	Angle   float64
	PGen    float64
	QGen    float64
	QMin    float64
	QMax    float64
	PLoad   float64
	QLoad   float64
	GShunt  float64
	BShunt  float64
}

// BranchStatus is IN or OUT.
type BranchStatus string

const (
	BranchIN  BranchStatus = "IN"
	BranchOUT BranchStatus = "OUT"
)

// BranchRecord is one BRANCH line.
type BranchRecord struct {
	ID       string
	From     string
	To       string
	Status   BranchStatus
	R        float64
	X        float64
	BTotal   float64
	Tap      float64
	ShiftDeg float64
}

// Network is a validated AC network deck.
type Network struct {
	BaseMVA  float64
	Buses    []BusRecord
	Branches []BranchRecord
}

// LoadNetwork reads and validates a network deck from an absolute path.
func LoadNetwork(path string) (*Network, error) {
	if path == "" || !strings.HasPrefix(path, "/") {
		return nil, fmt.Errorf("%s", "network path must be absolute")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("cannot read network: %w", err)
	}
	return ParseNetwork(string(data))
}

// ParseNetwork validates POWER-01 through POWER-03 field constraints (island checked later).
func ParseNetwork(text string) (*Network, error) {
	lines, err := ScanLines(strings.NewReader(text))
	if err != nil {
		return nil, err
	}
	if len(lines) == 0 {
		return nil, fmt.Errorf("empty network deck")
	}
	hdr := Tokens(lines[0])
	if len(hdr) != 2 || hdr[0] != "AC_NETWORK" || hdr[1] != "1" {
		return nil, fmt.Errorf("expected AC_NETWORK 1 header")
	}

	var (
		baseSet bool
		base    float64
		buses   []BusRecord
		brs     []BranchRecord
		busIDs  = map[string]struct{}{}
		brIDs   = map[string]struct{}{}
		ended   bool
	)

	for i := 1; i < len(lines); i++ {
		toks := Tokens(lines[i])
		if len(toks) == 0 {
			continue
		}
		if ended {
			return nil, fmt.Errorf("data after END")
		}
		switch toks[0] {
		case "END":
			if len(toks) != 1 {
				return nil, fmt.Errorf("END has trailing tokens")
			}
			ended = true
		case "BASE_MVA":
			if baseSet || len(toks) != 2 {
				return nil, fmt.Errorf("invalid BASE_MVA")
			}
			v, err := ParseFloat(toks[1])
			if err != nil || v <= 0 {
				return nil, fmt.Errorf("invalid BASE_MVA value")
			}
			base = v
			baseSet = true
		case "BUS":
			if len(toks) != 13 {
				return nil, fmt.Errorf("BUS arity")
			}
			id := toks[1]
			if !ValidID(id) {
				return nil, fmt.Errorf("bad bus id")
			}
			if _, ok := busIDs[id]; ok {
				return nil, fmt.Errorf("duplicate bus %s", id)
			}
			bt := BusType(toks[2])
			if bt != BusSlack && bt != BusPV && bt != BusPQ {
				return nil, fmt.Errorf("bad bus type")
			}
			vals := make([]float64, 10)
			for j := 0; j < 10; j++ {
				vals[j], err = ParseFloat(toks[3+j])
				if err != nil {
					return nil, fmt.Errorf("bad bus number")
				}
			}
			b := BusRecord{
				ID: id, Type: bt,
				VSet: vals[0], Angle: vals[1], PGen: vals[2], QGen: vals[3],
				QMin: vals[4], QMax: vals[5], PLoad: vals[6], QLoad: vals[7],
				GShunt: vals[8], BShunt: vals[9],
			}
			if b.VSet <= 0 || b.QMin > b.QGen || b.QGen > b.QMax || b.PLoad < 0 || b.QLoad < 0 {
				return nil, fmt.Errorf("bus semantic failure")
			}
			if b.Type == BusPQ && (b.QMin != b.QGen || b.QMax != b.QGen) {
				return nil, fmt.Errorf("PQ q limits must equal q_gen")
			}
			busIDs[id] = struct{}{}
			buses = append(buses, b)
		case "BRANCH":
			if len(toks) != 10 {
				return nil, fmt.Errorf("BRANCH arity")
			}
			id := toks[1]
			if !ValidID(id) {
				return nil, fmt.Errorf("bad branch id")
			}
			if _, ok := brIDs[id]; ok {
				return nil, fmt.Errorf("duplicate branch %s", id)
			}
			st := BranchStatus(toks[4])
			if st != BranchIN && st != BranchOUT {
				return nil, fmt.Errorf("bad branch status")
			}
			nums := make([]float64, 5)
			for j := 0; j < 5; j++ {
				nums[j], err = ParseFloat(toks[5+j])
				if err != nil {
					return nil, err
				}
			}
			br := BranchRecord{
				ID: id, From: toks[2], To: toks[3], Status: st,
				R: nums[0], X: nums[1], BTotal: nums[2], Tap: nums[3], ShiftDeg: nums[4],
			}
			if br.R < 0 || br.X == 0 || br.Tap <= 0 || br.From == br.To {
				return nil, fmt.Errorf("branch semantic failure")
			}
			brIDs[id] = struct{}{}
			brs = append(brs, br)
		default:
			return nil, fmt.Errorf("unknown record %s", toks[0])
		}
	}
	if !ended {
		return nil, fmt.Errorf("missing END")
	}
	if !baseSet {
		return nil, fmt.Errorf("missing BASE_MVA")
	}
	nBus := len(buses)
	nBr := len(brs)
	if nBus < 2 || nBus > 30 || nBr < 1 || nBr > 60 {
		return nil, fmt.Errorf("bus/branch count out of range")
	}
	slack := 0
	for _, b := range buses {
		if b.Type == BusSlack {
			slack++
		}
	}
	if slack != 1 {
		return nil, fmt.Errorf("exactly one slack required")
	}
	for _, br := range brs {
		if _, ok := busIDs[br.From]; !ok {
			return nil, fmt.Errorf("unknown branch endpoint")
		}
		if _, ok := busIDs[br.To]; !ok {
			return nil, fmt.Errorf("unknown branch endpoint")
		}
	}
	sort.Slice(buses, func(i, j int) bool { return buses[i].ID < buses[j].ID })
	sort.Slice(brs, func(i, j int) bool { return brs[i].ID < brs[j].ID })
	return &Network{BaseMVA: base, Buses: buses, Branches: brs}, nil
}

// SlackID returns the unique slack bus identifier.
func (n *Network) SlackID() string {
	for _, b := range n.Buses {
		if b.Type == BusSlack {
			return b.ID
		}
	}
	return ""
}

// BusIndex maps id to index in sorted Buses.
func (n *Network) BusIndex() map[string]int {
	m := make(map[string]int, len(n.Buses))
	for i, b := range n.Buses {
		m[b.ID] = i
	}
	return m
}
