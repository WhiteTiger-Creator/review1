package deck

import (
	"fmt"
	"os"
	"sort"
	"strings"
)

// Demand is one DEMAND row.
type Demand struct {
	BusID  string
	DeltaP float64
	DeltaQ float64
}

// Ramp is a validated loading program.
type Ramp struct {
	Demands              []Demand
	VoltageMin           float64
	VoltageMax           float64
	StepInitial          float64
	StepMinimum          float64
	StepMaximum          float64
	PowerTolerance       float64
	ArcTolerance         float64
	ReactiveEventTol     float64
	FoldTolerance        float64
	BaseMaxIterations    int
	CorrectorMaxIters    int
	PointMax             int
}

// LoadRamp reads and validates a ramp deck from an absolute path against a network.
func LoadRamp(path string, net *Network) (*Ramp, error) {
	if path == "" || !strings.HasPrefix(path, "/") {
		return nil, fmt.Errorf("ramp path must be absolute")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("cannot read ramp: %w", err)
	}
	return ParseRamp(string(data), net)
}

// ParseRamp validates TRACE-01.
func ParseRamp(text string, net *Network) (*Ramp, error) {
	lines, err := ScanLines(strings.NewReader(text))
	if err != nil {
		return nil, err
	}
	if len(lines) == 0 {
		return nil, fmt.Errorf("empty ramp deck")
	}
	hdr := Tokens(lines[0])
	if len(hdr) != 2 || hdr[0] != "AC_RAMP" || hdr[1] != "1" {
		return nil, fmt.Errorf("expected AC_RAMP 1 header")
	}

	busSet := map[string]struct{}{}
	slack := net.SlackID()
	for _, b := range net.Buses {
		if b.ID != slack {
			busSet[b.ID] = struct{}{}
		}
	}

	r := &Ramp{}
	var (
		demands   []Demand
		seenDem   = map[string]struct{}{}
		haveLim   bool
		haveSteps bool
		haveTol   bool
		haveIter  bool
		ended     bool
	)

	for i := 1; i < len(lines); i++ {
		toks := Tokens(lines[i])
		if ended {
			return nil, fmt.Errorf("data after END")
		}
		switch toks[0] {
		case "END":
			if len(toks) != 1 {
				return nil, fmt.Errorf("END trailing")
			}
			ended = true
		case "DEMAND":
			if len(toks) != 4 {
				return nil, fmt.Errorf("DEMAND arity")
			}
			id := toks[1]
			if !ValidID(id) {
				return nil, fmt.Errorf("bad demand id")
			}
			if id == slack {
				return nil, fmt.Errorf("demand on slack")
			}
			if _, ok := busSet[id]; !ok {
				return nil, fmt.Errorf("unknown demand bus")
			}
			if _, ok := seenDem[id]; ok {
				return nil, fmt.Errorf("duplicate demand")
			}
			dp, err1 := ParseFloat(toks[2])
			dq, err2 := ParseFloat(toks[3])
			if err1 != nil || err2 != nil || dp < 0 || dq < 0 {
				return nil, fmt.Errorf("bad demand values")
			}
			seenDem[id] = struct{}{}
			demands = append(demands, Demand{BusID: id, DeltaP: dp, DeltaQ: dq})
		case "LIMITS":
			if haveLim || len(toks) != 3 {
				return nil, fmt.Errorf("LIMITS")
			}
			vmin, err1 := ParseFloat(toks[1])
			vmax, err2 := ParseFloat(toks[2])
			if err1 != nil || err2 != nil || vmin <= 0 || vmax <= 0 || !(vmin < vmax) {
				return nil, fmt.Errorf("bad limits")
			}
			r.VoltageMin, r.VoltageMax = vmin, vmax
			haveLim = true
		case "STEPS":
			if haveSteps || len(toks) != 4 {
				return nil, fmt.Errorf("STEPS")
			}
			a, e1 := ParseFloat(toks[1])
			b, e2 := ParseFloat(toks[2])
			c, e3 := ParseFloat(toks[3])
			if e1 != nil || e2 != nil || e3 != nil || a <= 0 || b <= 0 || c <= 0 || !(b <= a && a <= c) {
				return nil, fmt.Errorf("bad steps")
			}
			r.StepInitial, r.StepMinimum, r.StepMaximum = a, b, c
			haveSteps = true
		case "TOLERANCES":
			if haveTol || len(toks) != 5 {
				return nil, fmt.Errorf("TOLERANCES")
			}
			vals := make([]float64, 4)
			for j := 0; j < 4; j++ {
				vals[j], err = ParseFloat(toks[1+j])
				if err != nil || vals[j] <= 0 {
					return nil, fmt.Errorf("bad tolerances")
				}
			}
			r.PowerTolerance = vals[0]
			r.ArcTolerance = vals[1]
			r.ReactiveEventTol = vals[2]
			r.FoldTolerance = vals[3]
			haveTol = true
		case "ITERATIONS":
			if haveIter || len(toks) != 4 {
				return nil, fmt.Errorf("ITERATIONS")
			}
			bi, e1 := parseIntRange(toks[1], 2, 100)
			ci, e2 := parseIntRange(toks[2], 2, 100)
			pi, e3 := parseIntRange(toks[3], 8, 600)
			if e1 != nil || e2 != nil || e3 != nil {
				return nil, fmt.Errorf("bad iterations")
			}
			r.BaseMaxIterations, r.CorrectorMaxIters, r.PointMax = bi, ci, pi
			haveIter = true
		default:
			return nil, fmt.Errorf("unknown ramp record")
		}
	}
	if !ended || !haveLim || !haveSteps || !haveTol || !haveIter {
		return nil, fmt.Errorf("incomplete ramp")
	}
	if len(demands) != len(busSet) {
		return nil, fmt.Errorf("missing demand records")
	}
	for id := range busSet {
		if _, ok := seenDem[id]; !ok {
			return nil, fmt.Errorf("missing demand for %s", id)
		}
	}
	pos := false
	for _, d := range demands {
		if d.DeltaP > 0 || d.DeltaQ > 0 {
			pos = true
			break
		}
	}
	if !pos {
		return nil, fmt.Errorf("need positive demand direction")
	}
	sort.Slice(demands, func(i, j int) bool { return demands[i].BusID < demands[j].BusID })
	r.Demands = demands
	return r, nil
}

func parseIntRange(tok string, lo, hi int) (int, error) {
	v, err := ParseFloat(tok)
	if err != nil {
		return 0, err
	}
	iv := int(v)
	if float64(iv) != v || iv < lo || iv > hi {
		return 0, fmt.Errorf("int range")
	}
	return iv, nil
}

// DemandMap returns delta_p/q by bus id.
func (r *Ramp) DemandMap() map[string]Demand {
	m := make(map[string]Demand, len(r.Demands))
	for _, d := range r.Demands {
		m[d.BusID] = d
	}
	return m
}
