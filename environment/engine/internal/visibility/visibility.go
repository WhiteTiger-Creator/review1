package visibility

import (
	"sort"

	"signal-defense/internal/grid"
	"signal-defense/internal/threats"
)

type Contact struct {
	ID        string `json:"id"`
	Sector    string `json:"sector"`
	KindGuess string `json:"kind_guess"`
	Age       int    `json:"age"`
	Confirmed bool   `json:"confirmed"`
	FalseLikely bool `json:"false_likely"`
}

type Observer struct {
	PostID     string
	Sector     string
	ScanRange  int
	SensorBoost int
}

func LocalContacts(g *grid.Graph, obs Observer, active []*threats.Active, scanned map[string]bool) []Contact {
	out := []Contact{}
	for _, t := range active {
		if !t.Alive || t.Escaped || t.CapturedBy != "" {
			continue
		}
		sec := t.Sector()
		if sec == "" {
			continue
		}
		dist := g.Distance(obs.Sector, sec)
		rangeLimit := obs.ScanRange
		if scanned[sec] {
			rangeLimit += 1 + obs.SensorBoost
		}
		// Always see own sector and adjacent; scan extends.
		visible := dist >= 0 && dist <= 1
		if scanned[sec] || (dist >= 0 && dist <= rangeLimit && scanned[obs.Sector]) {
			visible = true
		}
		// If any scan targeted a neighbor path containing threat
		for s := range scanned {
			if s == sec || g.HasEdge(s, sec) {
				visible = true
			}
		}
		if !visible {
			continue
		}
		c := Contact{
			ID:     t.ID,
			Sector: sec,
			Age:    0,
		}
		if scanned[sec] || dist == 0 {
			c.Confirmed = true
			if t.Kind == threats.KindFalse {
				c.KindGuess = "false"
				c.FalseLikely = true
			} else {
				c.KindGuess = "incursion"
			}
			t.Confirmed = true
			t.Visible = true
		} else {
			c.KindGuess = "unknown"
			t.Visible = true
		}
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Sector != out[j].Sector {
			return out[i].Sector < out[j].Sector
		}
		return out[i].ID < out[j].ID
	})
	return out
}

func PublicContacts(agent, partner []Contact) []Contact {
	seen := map[string]Contact{}
	for _, c := range agent {
		seen[c.ID] = c
	}
	for _, c := range partner {
		prev, ok := seen[c.ID]
		if !ok {
			// partner-only contacts are NOT public to agent
			continue
		}
		if c.Confirmed {
			prev.Confirmed = true
			prev.KindGuess = c.KindGuess
			prev.FalseLikely = c.FalseLikely
			seen[c.ID] = prev
		}
	}
	out := make([]Contact, 0, len(seen))
	for _, c := range seen {
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Sector != out[j].Sector {
			return out[i].Sector < out[j].Sector
		}
		return out[i].ID < out[j].ID
	})
	return out
}
