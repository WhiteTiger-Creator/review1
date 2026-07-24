package decoy

import (
	"bytes"
	"encoding/json"
	"fmt"

	"loadcrest/internal/deck"
	"loadcrest/internal/grid"
)

// AdmittanceReport is the POWER-11 companion JSON.
type AdmittanceReport struct {
	Format              string             `json:"format"`
	NetworkSHA256       string             `json:"network_sha256"`
	BaseMVA             float64            `json:"base_mva"`
	BusCount            int                `json:"bus_count"`
	BranchCount         int                `json:"branch_count"`
	InServiceBranches   int                `json:"in_service_branch_count"`
	SlackBus            string             `json:"slack_bus"`
	NonzeroYEntries     int                `json:"nonzero_ybus_entries"`
	YBus                []yRow             `json:"ybus"`
	BranchPrimitives    []primitiveRow     `json:"branch_primitives"`
}

type yRow struct {
	Row string  `json:"row"`
	Col string  `json:"col"`
	G   float64 `json:"g"`
	B   float64 `json:"b"`
}

type primitiveRow struct {
	ID     string  `json:"id"`
	From   string  `json:"from"`
	To     string  `json:"to"`
	Status string  `json:"status"`
	Gff    float64 `json:"g_ff"`
	Bff    float64 `json:"b_ff"`
	Gft    float64 `json:"g_ft"`
	Bft    float64 `json:"b_ft"`
	Gtf    float64 `json:"g_tf"`
	Btf    float64 `json:"b_tf"`
	Gtt    float64 `json:"g_tt"`
	Btt    float64 `json:"b_tt"`
}

// RunAdmittance validates POWER-01..04 and prints canonical JSON.
func RunAdmittance(net *deck.Network) ([]byte, error) {
	buses := grid.BusesFromDeck(net)
	branches := grid.BranchesFromDeck(net)
	if err := grid.ValidateEnergizedIsland(buses, branches, net.SlackID()); err != nil {
		return nil, err
	}
	y := grid.BuildYBus(buses, branches)
	entries := grid.SortedYEntries(y)
	prims := grid.PrimitiveRows(branches)
	inSvc := 0
	for _, br := range branches {
		if br.Status == deck.BranchIN {
			inSvc++
		}
	}
	rep := AdmittanceReport{
		Format:            "admittance-companion-v1",
		NetworkSHA256:     deck.NetworkSHA256(net),
		BaseMVA:           net.BaseMVA,
		BusCount:          len(buses),
		BranchCount:       len(branches),
		InServiceBranches: inSvc,
		SlackBus:          net.SlackID(),
		NonzeroYEntries:   len(entries),
	}
	for _, e := range entries {
		rep.YBus = append(rep.YBus, yRow{Row: e.Row, Col: e.Col, G: e.G, B: e.B})
	}
	for _, p := range prims {
		rep.BranchPrimitives = append(rep.BranchPrimitives, primitiveRow{
			ID: p.ID, From: p.From, To: p.To, Status: p.Status,
			Gff: p.Gff, Bff: p.Bff, Gft: p.Gft, Bft: p.Bft,
			Gtf: p.Gtf, Btf: p.Btf, Gtt: p.Gtt, Btt: p.Btt,
		})
	}
	buf := &bytes.Buffer{}
	enc := json.NewEncoder(buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(rep); err != nil {
		return nil, fmt.Errorf("encode: %w", err)
	}
	return buf.Bytes(), nil
}
