package cooperation

import (
	"sort"

	"signal-defense/internal/orders"
	"signal-defense/internal/signaling"
	"signal-defense/internal/visibility"
)

const (
	DoctrineSignalExplicit    = "signal-explicit"
	DoctrinePowerConservative = "power-conservative"
	DoctrineAggressive        = "aggressive"
)

type PartnerState struct {
	Doctrine   string
	Sector     string
	PostID     string
	TokensLeft int
	Battery    int
	LastCover  string
	Intents    []string
}

type Context struct {
	Round       int
	Contacts    []visibility.Contact
	SignalsIn   []signaling.Message
	GeneratorOK bool
	Overloaded  bool
	Civilian    []string
	Horizon     int
	CanSync     bool
	SyncSector  string
}

func Decide(st PartnerState, ctx Context) (orders.Bundle, PartnerState) {
	acts := []orders.Action{}
	switch st.Doctrine {
	case DoctrinePowerConservative:
		acts, st = powerConservative(st, ctx)
	case DoctrineAggressive:
		acts, st = aggressive(st, ctx)
	default:
		acts, st = signalExplicit(st, ctx)
	}
	if len(acts) == 0 {
		acts = []orders.Action{{Op: orders.OpHold}}
	}
	return orders.Bundle{Round: ctx.Round, Actor: st.PostID, Actions: acts}, st
}

func signalExplicit(st PartnerState, ctx Context) ([]orders.Action, PartnerState) {
	acts := []orders.Action{}
	// Acknowledge delayed warnings.
	for _, msg := range ctx.SignalsIn {
		if msg.Type == "WARN_LANE" || msg.Type == "SYNC_CAPTURE" {
			if st.TokensLeft > 0 {
				acts = append(acts, orders.Action{
					Op: orders.OpSignal,
					Msg: map[string]any{
						"type":    "ACK",
						"sector":  msg.Sector,
						"contact": msg.Contact,
						"ref":     msg.ID,
					},
				})
				st.TokensLeft--
			}
		}
	}
	// Prioritize synchronized capture movement/intercept.
	if ctx.CanSync && ctx.SyncSector != "" {
		if st.TokensLeft > 0 {
			acts = append(acts, orders.Action{
				Op: orders.OpSignal,
				Msg: map[string]any{"type": "SYNC_CAPTURE", "sector": ctx.SyncSector},
			})
			st.TokensLeft--
		}
		if ctx.SyncSector == st.Sector {
			acts = append(acts, orders.Action{Op: orders.OpIntercept, Contact: "boss", Target: ctx.SyncSector})
		} else {
			acts = append(acts, orders.Action{Op: orders.OpMove, Target: ctx.SyncSector})
			acts = append(acts, orders.Action{Op: orders.OpIntercept, Contact: "boss", Target: ctx.SyncSector})
		}
		return dedupe(acts), st
	}
	// Warn about confirmed incursions.
	for _, c := range ctx.Contacts {
		if c.Confirmed && !c.FalseLikely && st.TokensLeft > 0 {
			acts = append(acts, orders.Action{
				Op: orders.OpSignal,
				Msg: map[string]any{"type": "WARN_LANE", "sector": c.Sector, "contact": c.ID},
			})
			st.TokensLeft--
			break
		}
	}
	// Cover nearest confirmed contact.
	if c := nearestConfirmed(ctx.Contacts); c != nil {
		if c.Sector == st.Sector {
			acts = append(acts, orders.Action{Op: orders.OpIntercept, Contact: c.ID, Target: c.Sector})
			st.LastCover = c.ID
		} else {
			acts = append(acts, orders.Action{Op: orders.OpMove, Target: stepToward(st.Sector, c.Sector, ctx)})
			acts = append(acts, orders.Action{Op: orders.OpScan, Target: c.Sector})
		}
	} else if len(ctx.Contacts) > 0 {
		acts = append(acts, orders.Action{Op: orders.OpScan, Target: ctx.Contacts[0].Sector})
	} else {
		acts = append(acts, orders.Action{Op: orders.OpHold})
	}
	return dedupe(acts), st
}

func powerConservative(st PartnerState, ctx Context) ([]orders.Action, PartnerState) {
	acts := []orders.Action{}
	if ctx.Overloaded {
		acts = append(acts, orders.Action{Op: orders.OpRepair, Target: "linked"})
		acts = append(acts, orders.Action{Op: orders.OpHold})
		return acts, st
	}
	// Prefer hold/move without scanning unless confirmed threat near.
	if c := nearestConfirmed(ctx.Contacts); c != nil && !c.FalseLikely {
		if c.Sector == st.Sector {
			acts = append(acts, orders.Action{Op: orders.OpIntercept, Contact: c.ID, Target: c.Sector})
		} else {
			acts = append(acts, orders.Action{Op: orders.OpMove, Target: stepToward(st.Sector, c.Sector, ctx)})
		}
		// Signal need power sparingly
		if st.Battery < 2 && st.TokensLeft > 0 {
			acts = append(acts, orders.Action{Op: orders.OpSignal, Msg: map[string]any{"type": "NEED_POWER"}})
			st.TokensLeft--
		}
	} else {
		acts = append(acts, orders.Action{Op: orders.OpHold})
		if st.TokensLeft > 0 && ctx.Round%3 == 0 {
			acts = append(acts, orders.Action{Op: orders.OpSignal, Msg: map[string]any{"type": "STATUS", "sector": st.Sector}})
			st.TokensLeft--
		}
	}
	return dedupe(acts), st
}

func aggressive(st PartnerState, ctx Context) ([]orders.Action, PartnerState) {
	acts := []orders.Action{}
	// Burn power early: scan and intercept everything visible.
	for _, c := range ctx.Contacts {
		acts = append(acts, orders.Action{Op: orders.OpScan, Target: c.Sector})
		if c.Sector == st.Sector || true {
			acts = append(acts, orders.Action{Op: orders.OpIntercept, Contact: c.ID, Target: c.Sector})
		}
		if len(acts) >= 3 {
			break
		}
	}
	if len(ctx.Civilian) > 0 {
		acts = append(acts, orders.Action{Op: orders.OpShield, Target: ctx.Civilian[0]})
	}
	if len(acts) == 0 {
		acts = append(acts, orders.Action{Op: orders.OpHold})
	}
	return dedupe(acts), st
}

func nearestConfirmed(cs []visibility.Contact) *visibility.Contact {
	var best *visibility.Contact
	for i := range cs {
		c := &cs[i]
		if !c.Confirmed || c.FalseLikely {
			continue
		}
		if best == nil || c.ID < best.ID {
			best = c
		}
	}
	return best
}

func stepToward(from, to string, ctx Context) string {
	// Doctrine uses target directly; engine validates adjacency and clamps.
	_ = ctx
	if to == "" {
		return from
	}
	return to
}

func dedupe(acts []orders.Action) []orders.Action {
	seen := map[string]bool{}
	out := []orders.Action{}
	for _, a := range acts {
		key := a.Op + "|" + a.Target + "|" + a.Contact
		if a.Op == orders.OpSignal {
			t, _ := a.Msg["type"].(string)
			key = a.Op + "|" + t
		}
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, a)
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Op != out[j].Op {
			return out[i].Op < out[j].Op
		}
		return out[i].Target < out[j].Target
	})
	return out
}

func KnownDoctrines() []string {
	return []string{DoctrineSignalExplicit, DoctrinePowerConservative, DoctrineAggressive}
}
