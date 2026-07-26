package sortie

import (
	"encoding/json"
	"os"
	"sort"

	"orbsalvage/osflib/burn"
	"orbsalvage/osflib/hold"
	"orbsalvage/osflib/signal"
)

type Orbit struct {
	OrbitID string `json:"orbit_id"`
	Radius  int    `json:"radius"`
}

type Window struct {
	FromOrbit string `json:"from_orbit"`
	ToOrbit   string `json:"to_orbit"`
	OpenTick  int    `json:"open_tick"`
	CloseTick int    `json:"close_tick"`
}

type WreckIn struct {
	WreckID string `json:"wreck_id"`
	OrbitID string `json:"orbit_id"`
	Mass    int    `json:"mass"`
}

type Order struct {
	Seq     int    `json:"seq"`
	OrderID string `json:"order_id"`
	Kind    string `json:"kind"`
	CraftID string `json:"craft_id"`
	OrbitID string `json:"orbit_id"`
	ToOrbit string `json:"to_orbit"`
	WreckID string `json:"wreck_id"`
	Ticks   int    `json:"ticks"`
	Mass    int    `json:"mass"`
}

type Mission struct {
	SortieID           string                 `json:"sortie_id"`
	Seed               int                    `json:"seed"`
	FuelBudget         int                    `json:"fuel_budget"`
	HoldCapacity       int                    `json:"hold_capacity"`
	ClawDurability     int                    `json:"claw_durability"`
	CommBlackoutTicks  int                    `json:"comm_blackout_ticks"`
	MaxTicks           int                    `json:"max_ticks"`
	BurnScale          int                    `json:"burn_scale"`
	WearPerGrapple     int                    `json:"wear_per_grapple"`
	DebrisThreshold    int                    `json:"debris_threshold"`
	PolicyOverrides    map[string]interface{} `json:"policy_overrides"`
	Orbits             []Orbit                `json:"orbits"`
	Windows            []Window               `json:"windows"`
	Wrecks             []WreckIn              `json:"wrecks"`
	Orders             []Order                `json:"orders"`
}

type CraftOut struct {
	CraftID  string `json:"craft_id"`
	OrbitID  string `json:"orbit_id"`
	Fuel     int    `json:"fuel"`
	HoldUsed int    `json:"hold_used"`
	Claw     int    `json:"claw"`
	State    string `json:"state"`
}

type Incident struct {
	IncidentID string `json:"incident_id"`
	Code       string `json:"code"`
	EntityID   string `json:"entity_id"`
	OrderSeq   int    `json:"order_seq"`
	Detail     string `json:"detail"`
}

type SortieOut struct {
	SortieID                string     `json:"sortie_id"`
	Status                  string     `json:"status"`
	TicksElapsed            int        `json:"ticks_elapsed"`
	FuelRemaining           int        `json:"fuel_remaining"`
	HoldUsed                int        `json:"hold_used"`
	WrecksRecovered         int        `json:"wrecks_recovered"`
	DuplicateOrdersSkipped  int        `json:"duplicate_orders_skipped"`
	Crafts                  []CraftOut `json:"crafts"`
	Incidents               []Incident `json:"incidents"`
}

type Report struct {
	Sorties []SortieOut `json:"sorties"`
}

type craftState struct {
	craftID   string
	orbitID   string
	fuel      int
	holdUsed  int
	claw      int
	state     string
	attached  string
	lastRelay int
}

type wreckState struct {
	orbitID    string
	mass       int
	recovered  bool
	attachedTo string
}

func LoadMission(path string) (Mission, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Mission{}, err
	}
	var m Mission
	if err := json.Unmarshal(raw, &m); err != nil {
		return Mission{}, err
	}
	return m, nil
}

func formatSeq(seq int) string {
	if seq < 0 {
		seq = 0
	}
	s := []byte("0000")
	n := seq
	for i := 3; i >= 0; i-- {
		s[i] = byte('0' + n%10)
		n /= 10
	}
	return string(s)
}

func appendIncident(inc *[]Incident, sortieID, entity, code, detail string, seq int) {
	*inc = append(*inc, Incident{
		IncidentID: sortieID + "__" + entity + "__" + formatSeq(seq),
		Code:       code,
		EntityID:   entity,
		OrderSeq:   seq,
		Detail:     detail,
	})
}

func isFatal(code string) bool {
	switch code {
	case "FUEL_EXHAUSTED", "HOLD_OVERFLOW", "WINDOW_CLOSED", "DEBRIS_STRIKE", "RELAY_LOST", "CLAW_JAMMED", "SORTIE_TIMEOUT":
		return true
	default:
		return false
	}
}

func windowOpen(windows []Window, from, to string, tick int) bool {
	for _, w := range windows {
		if w.FromOrbit == from && w.ToOrbit == to && w.OpenTick <= tick && tick < w.CloseTick {
			return true
		}
	}
	return false
}

func Analyze(m Mission) SortieOut {
	burnScale := m.BurnScale
	if burnScale == 0 {
		burnScale = 10
	}
	wear := m.WearPerGrapple
	if wear == 0 {
		wear = 15
	}
	debrisThreshold := m.DebrisThreshold
	if debrisThreshold == 0 {
		debrisThreshold = 70
	}
	blackout := m.CommBlackoutTicks
	if blackout == 0 {
		blackout = 3
	}
	burnScale = burn.ApplyOverrides(burnScale, m.PolicyOverrides)
	wear = hold.ApplyWearOverrides(wear, m.PolicyOverrides)
	debrisThreshold, blackout = signal.ApplySignalOverrides(debrisThreshold, blackout, m.PolicyOverrides)

	orbits := map[string]int{}
	for _, o := range m.Orbits {
		orbits[o.OrbitID] = o.Radius
	}
	wrecks := map[string]*wreckState{}
	for _, w := range m.Wrecks {
		wrecks[w.WreckID] = &wreckState{orbitID: w.OrbitID, mass: w.Mass}
	}

	crafts := map[string]*craftState{}
	incidents := make([]Incident, 0)
	dupSkipped := 0
	seen := map[string]struct{}{}
	tick := 0
	closed := false
	fatal := false

	orders := append([]Order(nil), m.Orders...)
	sort.Slice(orders, func(i, j int) bool {
		if orders[i].Seq != orders[j].Seq {
			return orders[i].Seq < orders[j].Seq
		}
		if orders[i].OrderID != orders[j].OrderID {
			return orders[i].OrderID < orders[j].OrderID
		}
		return orders[i].Kind < orders[j].Kind
	})

	note := func(code, entity, detail string, seq int) {
		appendIncident(&incidents, m.SortieID, entity, code, detail, seq)
		if isFatal(code) {
			fatal = true
		}
	}

	for _, order := range orders {
		if closed || fatal {
			break
		}
		seq := order.Seq
		if order.OrderID != "" {
			seen[order.OrderID] = struct{}{}
		}

		switch order.Kind {
		case "LAUNCH_CRAFT":
			if _, ok := crafts[order.CraftID]; ok {
				note("CRAFT_DUP", order.CraftID, "", seq)
				continue
			}
			if _, ok := orbits[order.OrbitID]; !ok {
				note("ORBIT_UNKNOWN", order.OrbitID, "LAUNCH_CRAFT", seq)
				continue
			}
			crafts[order.CraftID] = &craftState{
				craftID:   order.CraftID,
				orbitID:   order.OrbitID,
				fuel:      m.FuelBudget,
				claw:      m.ClawDurability,
				state:     "active",
				lastRelay: -1000000000,
			}
		case "COAST_WAIT":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			wait := order.Ticks
			if wait <= 0 {
				wait = 1
			}
			tick += wait
			if tick > m.MaxTicks {
				note("SORTIE_TIMEOUT", order.CraftID, itoa(tick), seq)
				cr.state = "dead"
			}
		case "TRANSFER_BURN":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			if _, ok := orbits[order.ToOrbit]; !ok {
				note("ORBIT_UNKNOWN", order.ToOrbit, "TRANSFER_BURN", seq)
				continue
			}
			if _, ok := orbits[cr.orbitID]; !ok {
				note("ORBIT_UNKNOWN", cr.orbitID, "TRANSFER_BURN", seq)
				continue
			}
			if !windowOpen(m.Windows, cr.orbitID, order.ToOrbit, tick) {
				note("WINDOW_CLOSED", order.CraftID, cr.orbitID+">"+order.ToOrbit, seq)
				cr.state = "stranded"
				continue
			}
			cost := burn.Cost(orbits[cr.orbitID], orbits[order.ToOrbit], burnScale)
			if cr.fuel < cost {
				note("FUEL_EXHAUSTED", order.CraftID, itoa(cost), seq)
				cr.state = "dead"
				continue
			}
			cr.fuel -= cost
			cr.orbitID = order.ToOrbit
			tick++
		case "DEBRIS_SWEEP":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			roll := signal.DebrisRoll(m.Seed, tick, order.CraftID)
			if signal.Strike(roll, debrisThreshold) {
				note("DEBRIS_STRIKE", order.CraftID, itoa(roll), seq)
				cr.state = "dead"
			}
		case "GRAPPLE_WRECK":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			wk, ok := wrecks[order.WreckID]
			if !ok {
				note("WRECK_MISSING", order.WreckID, "", seq)
				continue
			}
			if wk.recovered || wk.attachedTo != "" {
				note("WRECK_MISSING", order.WreckID, "taken", seq)
				continue
			}
			if wk.orbitID != cr.orbitID {
				note("WRECK_MISSING", order.WreckID, "orbit", seq)
				continue
			}
			cr.claw -= wear
			if cr.claw < 0 {
				note("CLAW_JAMMED", order.CraftID, itoa(cr.claw), seq)
				cr.state = "dead"
				continue
			}
			wk.attachedTo = order.CraftID
			cr.attached = order.WreckID
		case "STOW_MASS":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			if cr.attached == "" {
				note("MASS_REJECT", order.CraftID, "", seq)
				continue
			}
			wk := wrecks[cr.attached]
			if hold.WouldOverflow(cr.holdUsed, wk.mass, m.HoldCapacity) {
				note("HOLD_OVERFLOW", order.CraftID, itoa(wk.mass), seq)
				cr.state = "dead"
				continue
			}
			cr.holdUsed += wk.mass
			wk.recovered = true
			wk.attachedTo = ""
			cr.attached = ""
		case "RELAY_PING":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			cr.lastRelay = tick
		case "JETTISON_BALLAST":
			cr, ok := crafts[order.CraftID]
			if !ok || cr.state != "active" {
				continue
			}
			if order.Mass > cr.holdUsed {
				note("BALLAST_EMPTY", order.CraftID, itoa(order.Mass), seq)
				continue
			}
			cr.holdUsed -= order.Mass
		case "CLOSE_SORTIE":
			if tick > m.MaxTicks {
				note("SORTIE_TIMEOUT", m.SortieID, itoa(tick), seq)
				closed = true
				break
			}
			for _, cr := range crafts {
				if cr.state != "active" {
					continue
				}
				if signal.RelayLost(tick, cr.lastRelay, blackout) {
					note("RELAY_LOST", cr.craftID, itoa(tick-cr.lastRelay), seq)
				}
			}
			closed = true
		}
	}

	recovered := 0
	for _, w := range wrecks {
		if w.recovered {
			recovered++
		}
	}
	fuelRemaining := 0
	holdUsed := 0
	if len(crafts) == 0 {
		fuelRemaining = m.FuelBudget
	}
	craftOut := make([]CraftOut, 0, len(crafts))
	ids := make([]string, 0, len(crafts))
	for id := range crafts {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		cr := crafts[id]
		fuelRemaining += cr.fuel
		holdUsed += cr.holdUsed
		craftOut = append(craftOut, CraftOut{
			CraftID:  cr.craftID,
			OrbitID:  cr.orbitID,
			Fuel:     cr.fuel,
			HoldUsed: cr.holdUsed,
			Claw:     cr.claw,
			State:    cr.state,
		})
	}
	sort.Slice(incidents, func(i, j int) bool {
		return incidents[i].IncidentID < incidents[j].IncidentID
	})

	status := "RECOVERED"
	if fatal || recovered < len(wrecks) || !closed {
		status = "FAILED"
	}

	return SortieOut{
		SortieID:               m.SortieID,
		Status:                 status,
		TicksElapsed:           tick,
		FuelRemaining:          fuelRemaining,
		HoldUsed:               holdUsed,
		WrecksRecovered:        recovered,
		DuplicateOrdersSkipped: dupSkipped,
		Crafts:                 craftOut,
		Incidents:              incidents,
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	buf := make([]byte, 0, 12)
	for n > 0 {
		buf = append(buf, byte('0'+n%10))
		n /= 10
	}
	if neg {
		buf = append(buf, '-')
	}
	for i, j := 0, len(buf)-1; i < j; i, j = i+1, j-1 {
		buf[i], buf[j] = buf[j], buf[i]
	}
	return string(buf)
}
