package match

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"signal-defense/internal/campaign"
	"signal-defense/internal/cooperation"
	"signal-defense/internal/grid"
	"signal-defense/internal/integrity"
	"signal-defense/internal/orders"
	"signal-defense/internal/power"
	"signal-defense/internal/protocol"
	"signal-defense/internal/replay"
	"signal-defense/internal/signaling"
	"signal-defense/internal/threats"
	"signal-defense/internal/visibility"
)

type Scenario struct {
	Name               string              `json:"name"`
	Seed               int64               `json:"seed"`
	Horizon            int                 `json:"horizon"`
	Sectors            []grid.Sector       `json:"sectors"`
	Edges              [][]string          `json:"edges"`
	AgentPost          PostSpec            `json:"agent_post"`
	PartnerPost        PostSpec            `json:"partner_post"`
	Generators         []power.Generator   `json:"generators"`
	CivilianCorridors  [][]string          `json:"civilian_corridors"`
	SignalBudget       int                 `json:"signal_budget"`
	SignalTypes        []string            `json:"signal_types"`
	Jamming            []JamPhase          `json:"jamming"`
	Waves              []threats.Spec      `json:"waves"`
	PartnerDoctrine    string              `json:"partner_doctrine"`
	Scoring            campaign.Weights    `json:"scoring"`
	Modifiers          map[string]any      `json:"modifiers"`
	MaxActions         int                 `json:"max_actions"`
	ScanRange          int                 `json:"scan_range"`
	InterceptorRange   int                 `json:"interceptor_range"`
	AcceptScore        int                 `json:"accept_score"`
	SyncCaptureContact string              `json:"sync_capture_contact"`
}

type PostSpec struct {
	ID      string `json:"id"`
	Sector  string `json:"sector"`
	Battery int    `json:"battery"`
	BatteryMax int `json:"battery_max"`
}

type JamPhase struct {
	Round    int `json:"round"`
	Duration int `json:"duration"`
}

type Config struct {
	AssetRoot   string
	Scenario    Scenario
	BotDir      string
	OutputRoot  string
	InjectFail  string
	SkipCompile bool
	BotBinary   string
}

type postRuntime struct {
	ID     string
	Sector string
}

func LoadScenarioFile(path string) (Scenario, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return Scenario{}, err
	}
	var sc Scenario
	if err := json.Unmarshal(b, &sc); err != nil {
		return Scenario{}, err
	}
	return sc, ValidateScenario(sc)
}

func ValidateScenario(sc Scenario) error {
	if sc.Name == "" {
		return fmt.Errorf("scenario name required")
	}
	if sc.Horizon < 1 || sc.Horizon > 64 {
		return fmt.Errorf("horizon out of bounds")
	}
	g := grid.New()
	seen := map[string]bool{}
	for _, s := range sc.Sectors {
		if seen[s.ID] {
			return fmt.Errorf("duplicate sector %s", s.ID)
		}
		seen[s.ID] = true
		if err := g.AddSector(s.ID, s.X, s.Y, s.Role); err != nil {
			return err
		}
	}
	for _, e := range sc.Edges {
		if len(e) != 2 {
			return fmt.Errorf("bad edge")
		}
		if err := g.AddEdge(e[0], e[1]); err != nil {
			return err
		}
	}
	if sc.AgentPost.ID == "" || sc.PartnerPost.ID == "" {
		return fmt.Errorf("posts required")
	}
	if g.Sectors[sc.AgentPost.Sector] == nil || g.Sectors[sc.PartnerPost.Sector] == nil {
		return fmt.Errorf("post sector missing")
	}
	for _, gen := range sc.Generators {
		if gen.Capacity < 0 {
			return fmt.Errorf("negative power")
		}
		if g.Sectors[gen.Sector] == nil {
			return fmt.Errorf("generator sector missing")
		}
		if len(gen.Links) == 0 {
			return fmt.Errorf("invalid generator links")
		}
	}
	for _, w := range sc.Waves {
		if err := grid.ValidateLane(g, w.Lane); err != nil {
			return err
		}
		if w.Kind != "" && w.Kind != threats.KindIncursion && w.Kind != threats.KindFalse {
			return fmt.Errorf("bad threat kind")
		}
	}
	for _, t := range sc.SignalTypes {
		if strings.HasPrefix(t, "HIDDEN_") || t == "WAVE_PLAN" {
			return fmt.Errorf("malformed signal type")
		}
	}
	if sc.SignalBudget < 0 {
		return fmt.Errorf("negative signal budget")
	}
	doc := sc.PartnerDoctrine
	ok := false
	for _, d := range cooperation.KnownDoctrines() {
		if d == doc {
			ok = true
		}
	}
	if !ok && doc != "" {
		return fmt.Errorf("unknown doctrine %s", doc)
	}
	return nil
}

func VerifyAssets(assetRoot string) error {
	manifest := filepath.Join(assetRoot, "integrity", "manifest.json")
	return integrity.MustVerifyBefore(assetRoot, manifest)
}

func Run(cfg Config) (replay.Generation, error) {
	if cfg.AssetRoot != "" {
		if err := VerifyAssets(cfg.AssetRoot); err != nil {
			return replay.Generation{}, err
		}
	}
	sc := cfg.Scenario
	if err := ValidateScenario(sc); err != nil {
		return replay.Generation{}, err
	}
	if sc.MaxActions <= 0 {
		sc.MaxActions = 4
	}
	if sc.ScanRange <= 0 {
		sc.ScanRange = 1
	}
	if sc.InterceptorRange <= 0 {
		sc.InterceptorRange = 1
	}
	if sc.PartnerDoctrine == "" {
		sc.PartnerDoctrine = cooperation.DoctrineSignalExplicit
	}
	if sc.Scoring.Infrastructure == 0 && sc.Scoring.Civilian == 0 {
		sc.Scoring = campaign.DefaultWeights()
	}

	g := grid.New()
	for _, s := range sc.Sectors {
		_ = g.AddSector(s.ID, s.X, s.Y, s.Role)
	}
	for _, e := range sc.Edges {
		_ = g.AddEdge(e[0], e[1])
	}

	pwr := power.New()
	for _, gen := range sc.Generators {
		if err := pwr.AddGenerator(gen); err != nil {
			return replay.Generation{}, err
		}
	}
	amax := sc.AgentPost.BatteryMax
	if amax <= 0 {
		amax = 6
	}
	pmax := sc.PartnerPost.BatteryMax
	if pmax <= 0 {
		pmax = 6
	}
	pwr.AddBattery(sc.AgentPost.ID, sc.AgentPost.Battery, amax)
	pwr.AddBattery(sc.PartnerPost.ID, sc.PartnerPost.Battery, pmax)

	bus := signaling.NewBus(sc.SignalBudget, sc.SignalTypes, 128)
	camp := &campaign.State{
		Weights:          sc.Scoring,
		InfrastructureHP: len(sc.Sectors),
		CiviliansTotal:   len(campaign.CorridorSectors(sc.CivilianCorridors)),
		CiviliansSafe:    len(campaign.CorridorSectors(sc.CivilianCorridors)),
		GeneratorsTotal:  len(sc.Generators),
		GeneratorsAlive:  len(sc.Generators),
	}

	agent := postRuntime{ID: sc.AgentPost.ID, Sector: sc.AgentPost.Sector}
	partner := postRuntime{ID: sc.PartnerPost.ID, Sector: sc.PartnerPost.Sector}
	pst := cooperation.PartnerState{
		Doctrine:   sc.PartnerDoctrine,
		Sector:     partner.Sector,
		PostID:     partner.ID,
		TokensLeft: sc.SignalBudget,
		Battery:    sc.PartnerPost.Battery,
	}

	branch := map[string]threats.Spec{}
	for _, w := range sc.Waves {
		if len(w.BranchLane) > 0 {
			branch[w.ID] = w
		}
	}

	var active []*threats.Active
	rounds := []map[string]any{}
	signalRows := []map[string]any{}
	allContacts := map[string]any{}
	diag := map[string]any{"legal_rounds": 0, "protocol_errors": 0, "actions": 0}
	interceptClaims := map[string][]string{} // contact -> actors this round

	var bot *protocol.BotSession
	var cleanup func()
	bin := cfg.BotBinary
	if bin == "" && !cfg.SkipCompile {
		if cfg.InjectFail == "compile" {
			return replay.Generation{}, fmt.Errorf("injected compile failure")
		}
		var err error
		bin, cleanup, err = protocol.TempBotBinary(cfg.BotDir)
		if err != nil {
			return replay.Generation{}, err
		}
		defer cleanup()
	}
	if bin != "" {
		var err error
		bot, err = protocol.StartBot(bin, cfg.BotDir)
		if err != nil {
			return replay.Generation{}, err
		}
		defer bot.Close()
	}

	jamUntil := map[int]bool{}
	for _, j := range sc.Jamming {
		dur := j.Duration
		if dur < 1 {
			dur = 1
		}
		for r := j.Round; r < j.Round+dur; r++ {
			jamUntil[r] = true
		}
	}

	seeded := sc.Seed

	for round := 1; round <= sc.Horizon; round++ {
		pwr.TickRound()
		bus.AdvanceRound()
		if jamUntil[round] {
			bus.SetJammed(true)
		}
		spawned := threats.Spawn(sc.Waves, round)
		active = append(active, spawned...)

		agentScan := map[string]bool{}
		partnerScan := map[string]bool{}

		// Build preliminary contacts (pre-action visibility)
		agentObs := visibility.Observer{PostID: agent.ID, Sector: agent.Sector, ScanRange: sc.ScanRange}
		partnerObs := visibility.Observer{PostID: partner.ID, Sector: partner.Sector, ScanRange: sc.ScanRange}
		agentContacts := visibility.LocalContacts(g, agentObs, active, agentScan)
		partnerContacts := visibility.LocalContacts(g, partnerObs, active, partnerScan)

		civSecs := campaign.CorridorSectors(sc.CivilianCorridors)
		canSync := sc.SyncCaptureContact != ""
		syncSector := ""
		for _, t := range active {
			if t.ID == sc.SyncCaptureContact && t.Alive {
				syncSector = t.Sector()
				canSync = true
			}
		}

		obs := map[string]any{
			"type":          "observation",
			"round":         round,
			"seed":          seeded,
			"scenario":      sc.Name,
			"post":          agent.ID,
			"sector":        agent.Sector,
			"battery":       pwr.Batteries[agent.ID].Charge,
			"power_available": pwr.Available(agent.ID),
			"generators":    pwr.Snapshot()["generators"],
			"contacts":      agentContacts,
			"signals_in":    bus.DeliveredSorted(),
			"signal_tokens": sc.SignalBudget - bus.Used,
			"signal_budget": sc.SignalBudget,
			"civilian_corridors": sc.CivilianCorridors,
			"horizon":       sc.Horizon,
			"legal_ops":     orders.AllOps,
			"max_actions":   sc.MaxActions,
			"partner_public_sector": partner.Sector,
			"jammed":        bus.Jammed,
			"modifiers":     sc.Modifiers,
		}

		agentBundle := orders.Bundle{Round: round, Actor: agent.ID, Actions: []orders.Action{{Op: orders.OpHold}}}
		if bot != nil {
			if cfg.InjectFail == "protocol" {
				return replay.Generation{}, fmt.Errorf("injected protocol failure")
			}
			if err := bot.Send(obs); err != nil {
				return replay.Generation{}, err
			}
			resp, err := bot.Recv(3 * time.Second)
			if err != nil {
				diag["protocol_errors"] = asInt(diag["protocol_errors"]) + 1
				return replay.Generation{}, fmt.Errorf("bot protocol: %w", err)
			}
			agentBundle, err = parseBundle(resp, agent.ID, round)
			if err != nil {
				diag["protocol_errors"] = asInt(diag["protocol_errors"]) + 1
				return replay.Generation{}, err
			}
		}

		pctx := cooperation.Context{
			Round: round, Contacts: partnerContacts, SignalsIn: filterTo(bus.DeliveredSorted(), partner.ID),
			GeneratorOK: camp.GeneratorsAlive == camp.GeneratorsTotal,
			Overloaded:  anyDamaged(pwr),
			Civilian:    civSecs,
			Horizon:     sc.Horizon,
			CanSync:     canSync && syncSector != "",
			SyncSector:  syncSector,
		}
		partnerBundle, pst := cooperation.Decide(pst, pctx)
		pst.Sector = partner.Sector
		pst.Battery = pwr.Batteries[partner.ID].Charge

		if err := orders.ValidateBasic(agentBundle, sc.MaxActions); err != nil {
			return replay.Generation{}, fmt.Errorf("illegal agent orders: %w", err)
		}

		// Apply agent then partner with simultaneous semantics via staged effects.
		interceptClaims = map[string][]string{}
		type effect struct {
			actor string
			act   orders.Action
		}
		effects := []effect{}
		for _, a := range agentBundle.Actions {
			effects = append(effects, effect{agent.ID, a})
		}
		for _, a := range partnerBundle.Actions {
			effects = append(effects, effect{partner.ID, a})
		}
		phase := map[string]int{
			orders.OpMove: 1, orders.OpScan: 2, orders.OpSignal: 3,
			orders.OpReinforce: 4, orders.OpShield: 5, orders.OpRepair: 6,
			orders.OpIntercept: 7, orders.OpHold: 8,
		}
		sort.SliceStable(effects, func(i, j int) bool {
			pi, pj := phase[effects[i].act.Op], phase[effects[j].act.Op]
			if pi != pj {
				return pi < pj
			}
			if effects[i].actor != effects[j].actor {
				return effects[i].actor < effects[j].actor
			}
			if effects[i].act.Target != effects[j].act.Target {
				return effects[i].act.Target < effects[j].act.Target
			}
			return effects[i].act.Contact < effects[j].act.Contact
		})

		roundSignals := []map[string]any{}
		falseAlarms := 0
		shielded := map[string]bool{}
		scans := map[string]map[string]bool{"agent": {}, "partner": {}}

		for _, ef := range effects {
			actor := ef.actor
			a := ef.act
			secRef := &agent.Sector
			scanMap := agentScan
			if actor == partner.ID {
				secRef = &partner.Sector
				scanMap = partnerScan
			}
			cost := orders.PowerCost(a.Op)
			switch a.Op {
			case orders.OpHold:
				// noop
			case orders.OpMove:
				if g.HasEdge(*secRef, a.Target) || *secRef == a.Target {
					if err := pwr.Spend(actor, cost); err == nil {
						*secRef = a.Target
					}
				} else if g.Distance(*secRef, a.Target) > 0 {
					// step one hop toward target deterministically
					next := firstHop(g, *secRef, a.Target)
					if next != "" {
						if err := pwr.Spend(actor, cost); err == nil {
							*secRef = next
						}
					}
				}
			case orders.OpScan:
				if err := pwr.Spend(actor, cost); err == nil {
					scanMap[a.Target] = true
					if actor == agent.ID {
						scans["agent"][a.Target] = true
					} else {
						scans["partner"][a.Target] = true
					}
				}
			case orders.OpShield:
				if err := pwr.Spend(actor, cost); err == nil {
					shielded[a.Target] = true
				} else {
					// Attempt may overload if generator contended: force mark when load at capacity and both scan+shield
					for _, gen := range pwr.LinkedGenerators(actor) {
						if gen.Load+cost > gen.Capacity {
							gen.Load += cost
							gen.Overload = true
							gen.Damaged = true
							camp.GeneratorsAlive = countAlive(pwr)
						}
					}
				}
			case orders.OpReinforce:
				_ = pwr.Spend(actor, cost)
			case orders.OpRepair:
				for _, gid := range pwr.GeneratorIDs() {
					gref := pwr.Generators[gid]
					if gref.Damaged {
						_ = pwr.Repair(actor, gid)
						camp.GeneratorsAlive = countAlive(pwr)
						break
					}
				}
			case orders.OpIntercept:
				cid := a.Contact
				if cid == "" {
					cid = a.Target
				}
				distOK := false
				isFalse := false
				for _, t := range active {
					if t.ID != cid || !t.Alive {
						continue
					}
					d := g.Distance(*secRef, t.Sector())
					if d >= 0 && d <= sc.InterceptorRange {
						distOK = true
					}
					if t.Kind == threats.KindFalse && scanMap[t.Sector()] {
						isFalse = true
					}
				}
				if distOK && !isFalse {
					if err := pwr.Spend(actor, cost); err == nil {
						interceptClaims[cid] = append(interceptClaims[cid], actor)
					}
				} else if distOK && isFalse {
					// Recognized false after scan: skip intercept (no claim, no false alarm)
				} else if distOK {
					if err := pwr.Spend(actor, cost); err == nil {
						interceptClaims[cid] = append(interceptClaims[cid], actor)
					}
				}
			case orders.OpSignal:
				msgType, _ := a.Msg["type"].(string)
				sector, _ := a.Msg["sector"].(string)
				contact, _ := a.Msg["contact"].(string)
				to := partner.ID
				if actor == partner.ID {
					to = agent.ID
				}
				msg, err := bus.Enqueue(actor, to, msgType, sector, contact, a.Msg, round)
				row := map[string]any{
					"id": msg.ID, "from": actor, "to": to, "type": msgType,
					"sector": sector, "contact": contact, "round": round,
					"accepted": err == nil, "error": errString(err),
				}
				roundSignals = append(roundSignals, row)
				signalRows = append(signalRows, row)
			}
		}
		pwr.MarkOverloadIfExceeded()
		camp.GeneratorsAlive = countAlive(pwr)

		// Resolve intercepts after simultaneous claims
		for _, t := range active {
			if !t.Alive {
				continue
			}
			claimers := uniqueSorted(interceptClaims[t.ID])
			if len(claimers) == 0 {
				continue
			}
			if t.Kind == threats.KindFalse {
				falseAlarms++
				t.Alive = false
				t.CapturedBy = claimers[0]
				continue
			}
			// Synchronized capture if required contact and both claim
			if sc.SyncCaptureContact == t.ID {
				if len(claimers) >= 2 {
					t.Alive = false
					t.CapturedBy = "sync"
					camp.SyncCaptures++
				}
				// single claimer cannot finish a sync-designated threat
				continue
			}
			// Redundant coverage: first claimer by id captures; extras noted but same outcome
			t.HP--
			if t.HP <= 0 {
				t.Alive = false
				t.CapturedBy = claimers[0]
			}
		}
		camp.FalseAlarms += falseAlarms

		// Civilian risk: if incursion on corridor without shield, civilians hurt
		for _, t := range active {
			if !t.Alive || t.Kind != threats.KindIncursion {
				continue
			}
			sec := t.Sector()
			if contains(civSecs, sec) && !shielded[sec] {
				if camp.CiviliansSafe > 0 {
					camp.CiviliansSafe--
				}
			}
		}

		threats.Advance(active, branch)

		for _, t := range active {
			if t.Escaped && t.Kind == threats.KindIncursion {
				camp.Breakthroughs++
				camp.InfrastructureHP--
				if camp.InfrastructureHP < 0 {
					camp.InfrastructureHP = 0
				}
				t.Escaped = false // counted once
			}
		}

		// Refresh contacts after scans
		agentContacts = visibility.LocalContacts(g, visibility.Observer{PostID: agent.ID, Sector: agent.Sector, ScanRange: sc.ScanRange}, active, agentScan)
		partnerContacts = visibility.LocalContacts(g, visibility.Observer{PostID: partner.ID, Sector: partner.Sector, ScanRange: sc.ScanRange}, active, partnerScan)
		allContacts[fmt.Sprintf("round-%02d", round)] = map[string]any{
			"agent":   agentContacts,
			"partner_private_omitted": true,
		}

		camp.Recompute()
		diag["legal_rounds"] = asInt(diag["legal_rounds"]) + 1
		diag["actions"] = asInt(diag["actions"]) + len(agentBundle.Actions)

		rounds = append(rounds, map[string]any{
			"round":            round,
			"agent_sector":     agent.Sector,
			"partner_sector":   partner.Sector,
			"agent_actions":    normalizeActions(agentBundle.Actions),
			"partner_actions":  normalizeActions(partnerBundle.Actions),
			"intercepts":       interceptClaims,
			"signals":          roundSignals,
			"power":            pwr.Snapshot(),
			"score":            camp.Score,
			"breakthroughs":    camp.Breakthroughs,
			"false_alarms":     camp.FalseAlarms,
			"sync_captures":    camp.SyncCaptures,
			"civilians_safe":   camp.CiviliansSafe,
			"agent_contacts":   agentContacts,
			"jammed":           bus.Jammed,
		})

		pst.Sector = partner.Sector
		pst.TokensLeft = sc.SignalBudget - bus.Used
		if pst.TokensLeft < 0 {
			pst.TokensLeft = 0
		}
	}

	if bot != nil {
		_ = bot.Send(map[string]any{"type": "end", "score": camp.Score, "scenario": sc.Name})
	}

	camp.Recompute()
	summary := map[string]any{
		"scenario":           sc.Name,
		"seed":               sc.Seed,
		"partner_doctrine":   sc.PartnerDoctrine,
		"score":              camp.Score,
		"score_reconciled":   camp.Score,
		"horizon":            sc.Horizon,
		"breakthroughs":      camp.Breakthroughs,
		"false_alarms":       camp.FalseAlarms,
		"sync_captures":      camp.SyncCaptures,
		"civilians_safe":     camp.CiviliansSafe,
		"civilians_total":    camp.CiviliansTotal,
		"infrastructure_hp":  camp.InfrastructureHP,
		"generators_alive":   camp.GeneratorsAlive,
		"accept_score":       sc.AcceptScore,
		"passed_accept":      sc.AcceptScore > 0 && camp.Score >= sc.AcceptScore,
	}

	gen := replay.Generation{
		Summary:        summary,
		Rounds:         rounds,
		Contacts:       allContacts,
		Signals:        signalRows,
		Power:          pwr.Snapshot(),
		Civilians:      map[string]any{"safe": camp.CiviliansSafe, "total": camp.CiviliansTotal, "corridors": sc.CivilianCorridors},
		BotDiagnostics: diag,
	}

	if cfg.OutputRoot != "" {
		if _, err := replay.StageAndPublish(cfg.OutputRoot, gen, cfg.InjectFail); err != nil {
			return gen, err
		}
	}
	return gen, nil
}

func parseBundle(m map[string]any, actor string, round int) (orders.Bundle, error) {
	b := orders.Bundle{Round: round, Actor: actor}
	raw, ok := m["actions"].([]any)
	if !ok {
		return b, fmt.Errorf("orders missing actions")
	}
	for _, item := range raw {
		mm, ok := item.(map[string]any)
		if !ok {
			return b, fmt.Errorf("bad action")
		}
		a := orders.Action{
			Op:      str(mm["op"]),
			Target:  str(mm["target"]),
			Contact: str(mm["contact"]),
		}
		if msg, ok := mm["msg"].(map[string]any); ok {
			a.Msg = msg
		}
		b.Actions = append(b.Actions, a)
	}
	return orders.Normalize(b), nil
}

func str(v any) string {
	s, _ := v.(string)
	return s
}

func asInt(v any) int {
	switch t := v.(type) {
	case int:
		return t
	case float64:
		return int(t)
	default:
		return 0
	}
}

func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func filterTo(msgs []signaling.Message, to string) []signaling.Message {
	out := []signaling.Message{}
	for _, m := range msgs {
		if m.To == to {
			out = append(out, m)
		}
	}
	return out
}

func anyDamaged(p *power.System) bool {
	for _, id := range p.GeneratorIDs() {
		if p.Generators[id].Damaged {
			return true
		}
	}
	return false
}

func countAlive(p *power.System) int {
	n := 0
	for _, id := range p.GeneratorIDs() {
		if !p.Generators[id].Damaged {
			n++
		}
	}
	return n
}

func firstHop(g *grid.Graph, from, to string) string {
	if from == to {
		return from
	}
	best := ""
	bestDist := -1
	for _, n := range g.Neighbors(from) {
		d := g.Distance(n, to)
		if d < 0 {
			continue
		}
		if best == "" || d < bestDist || (d == bestDist && n < best) {
			best = n
			bestDist = d
		}
	}
	return best
}

func uniqueSorted(xs []string) []string {
	m := map[string]bool{}
	for _, x := range xs {
		m[x] = true
	}
	out := make([]string, 0, len(m))
	for x := range m {
		out = append(out, x)
	}
	sort.Strings(out)
	return out
}

func contains(xs []string, v string) bool {
	for _, x := range xs {
		if x == v {
			return true
		}
	}
	return false
}

func normalizeActions(acts []orders.Action) []map[string]any {
	out := []map[string]any{}
	for _, a := range acts {
		row := map[string]any{"op": a.Op}
		if a.Target != "" {
			row["target"] = a.Target
		}
		if a.Contact != "" {
			row["contact"] = a.Contact
		}
		if a.Msg != nil {
			row["msg"] = a.Msg
		}
		out = append(out, row)
	}
	return out
}

func ApplyRename(sc Scenario, mapping map[string]string) (Scenario, error) {
	g := grid.New()
	for _, s := range sc.Sectors {
		_ = g.AddSector(s.ID, s.X, s.Y, s.Role)
	}
	for _, e := range sc.Edges {
		_ = g.AddEdge(e[0], e[1])
	}
	ng, err := g.Rename(mapping)
	if err != nil {
		return sc, err
	}
	out := sc
	out.Sectors = nil
	for _, id := range ng.IDs() {
		s := ng.Sectors[id]
		out.Sectors = append(out.Sectors, *s)
	}
	out.Edges = nil
	seen := map[string]bool{}
	for _, a := range ng.IDs() {
		for _, b := range ng.Neighbors(a) {
			key := a + "|" + b
			rkey := b + "|" + a
			if seen[key] || seen[rkey] {
				continue
			}
			seen[key] = true
			out.Edges = append(out.Edges, []string{a, b})
		}
	}
	out.AgentPost.Sector = mapping[sc.AgentPost.Sector]
	out.PartnerPost.Sector = mapping[sc.PartnerPost.Sector]
	for i := range out.Generators {
		out.Generators[i].Sector = mapping[sc.Generators[i].Sector]
	}
	for i := range out.CivilianCorridors {
		for j := range out.CivilianCorridors[i] {
			out.CivilianCorridors[i][j] = mapping[sc.CivilianCorridors[i][j]]
		}
	}
	for i := range out.Waves {
		for j := range out.Waves[i].Lane {
			out.Waves[i].Lane[j] = mapping[sc.Waves[i].Lane[j]]
		}
		for j := range out.Waves[i].BranchLane {
			out.Waves[i].BranchLane[j] = mapping[sc.Waves[i].BranchLane[j]]
		}
	}
	return out, nil
}

func ApplyRotate(sc Scenario) Scenario {
	g := grid.New()
	for _, s := range sc.Sectors {
		_ = g.AddSector(s.ID, s.X, s.Y, s.Role)
	}
	for _, e := range sc.Edges {
		_ = g.AddEdge(e[0], e[1])
	}
	ng := g.Rotate90()
	out := sc
	out.Sectors = nil
	for _, id := range ng.IDs() {
		out.Sectors = append(out.Sectors, *ng.Sectors[id])
	}
	// edges unchanged by id
	return out
}
