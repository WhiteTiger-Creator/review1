package orders

import (
	"fmt"
	"sort"
)

const (
	OpMove      = "move"
	OpScan      = "scan"
	OpIntercept = "intercept"
	OpReinforce = "reinforce"
	OpShield    = "shield"
	OpSignal    = "signal"
	OpHold      = "hold"
	OpRepair    = "repair"
)

var AllOps = []string{OpMove, OpScan, OpIntercept, OpReinforce, OpShield, OpSignal, OpHold, OpRepair}

type Action struct {
	Op      string         `json:"op"`
	Target  string         `json:"target,omitempty"`
	Contact string         `json:"contact,omitempty"`
	Msg     map[string]any `json:"msg,omitempty"`
}

type Bundle struct {
	Round   int      `json:"round"`
	Actor   string   `json:"actor"`
	Actions []Action `json:"actions"`
}

func ValidOp(op string) bool {
	for _, x := range AllOps {
		if x == op {
			return true
		}
	}
	return false
}

func Normalize(b Bundle) Bundle {
	out := Bundle{Round: b.Round, Actor: b.Actor}
	acts := append([]Action(nil), b.Actions...)
	sort.SliceStable(acts, func(i, j int) bool {
		if acts[i].Op != acts[j].Op {
			return acts[i].Op < acts[j].Op
		}
		if acts[i].Target != acts[j].Target {
			return acts[i].Target < acts[j].Target
		}
		return acts[i].Contact < acts[j].Contact
	})
	out.Actions = acts
	return out
}

func ValidateBasic(b Bundle, maxActions int) error {
	if b.Round < 1 {
		return fmt.Errorf("invalid round")
	}
	if b.Actor == "" {
		return fmt.Errorf("missing actor")
	}
	if len(b.Actions) == 0 {
		return fmt.Errorf("no actions")
	}
	if len(b.Actions) > maxActions {
		return fmt.Errorf("too many actions")
	}
	for _, a := range b.Actions {
		if !ValidOp(a.Op) {
			return fmt.Errorf("illegal op %s", a.Op)
		}
		if a.Op == OpSignal {
			if a.Msg == nil {
				return fmt.Errorf("signal missing msg")
			}
			t, _ := a.Msg["type"].(string)
			if t == "" {
				return fmt.Errorf("signal missing type")
			}
		}
		if a.Op == OpMove || a.Op == OpScan || a.Op == OpShield || a.Op == OpReinforce {
			if a.Target == "" {
				return fmt.Errorf("%s missing target", a.Op)
			}
		}
		if a.Op == OpIntercept && a.Contact == "" && a.Target == "" {
			return fmt.Errorf("intercept missing contact/target")
		}
	}
	return nil
}

func PowerCost(op string) int {
	switch op {
	case OpScan:
		return 2
	case OpIntercept:
		return 3
	case OpShield:
		return 2
	case OpReinforce:
		return 1
	case OpRepair:
		return 2
	case OpMove:
		return 1
	default:
		return 0
	}
}
