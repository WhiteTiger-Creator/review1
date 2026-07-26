package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"chironym/internal/corpus"
	"chironym/internal/decoy"
	"chironym/internal/ledger"
	"chironym/internal/publish"
	"chironym/internal/riskgate"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: chironymctl <prepare|evaluate> ...")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "prepare":
		os.Exit(cmdPrepare(os.Args[2:]))
	case "evaluate":
		os.Exit(cmdEvaluate(os.Args[2:]))
	default:
		fmt.Fprintln(os.Stderr, "unknown command")
		os.Exit(2)
	}
}

func cmdPrepare(args []string) int {
	out := flagVal(args, "--output")
	if out == "" {
		fmt.Fprintln(os.Stderr, "missing --output")
		return 2
	}
	if err := os.MkdirAll(out, 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if err := os.MkdirAll("/app/var", 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	path := filepath.Join(out, "chironym_prepared.json")
	gen := 1
	if b, err := os.ReadFile(path); err == nil {
		var prev map[string]any
		if json.Unmarshal(b, &prev) == nil {
			if g, ok := prev["generation"].(float64); ok {
				gen = int(g) + 1
			}
		}
	}
	payload := map[string]any{"armed": true, "generation": gen}
	b, _ := json.MarshalIndent(payload, "", "  ")
	if err := os.WriteFile(path, b, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	_ = decoy.HintNoise([]float64{float64(gen)})
	return 0
}

func cmdEvaluate(args []string) int {
	camp := flagVal(args, "--campaign")
	out := flagVal(args, "--output")
	if camp == "" || out == "" {
		fmt.Fprintln(os.Stderr, "missing args")
		return 2
	}
	prep := filepath.Join(out, "chironym_prepared.json")
	b, err := os.ReadFile(prep)
	if err != nil {
		fmt.Fprintf(os.Stderr, "chironym output not armed: missing prepare marker\n")
		return 1
	}
	var marker map[string]any
	if json.Unmarshal(b, &marker) != nil || marker["armed"] != true {
		fmt.Fprintf(os.Stderr, "chironym output not armed: invalid marker\n")
		return 1
	}

	publish.ClearPrimary(out)

	pack, pol, packBytes, polBytes, err := corpus.Load(camp)
	if err != nil {
		fmt.Fprintf(os.Stderr, "invalid chironym campaign: %v\n", err)
		return 1
	}

	embedBin := envOr("CHIRONYM_EMBED_BIN", "/app/bin/k7")
	alignBin := envOr("CHIRONYM_ALIGN_BIN", "/app/bin/m3")
	pd, pold := riskgate.PackPolicyDigest(packBytes, polBytes)
	res, err := riskgate.DriveCampaign(pack, pol, pd, pold, embedBin, alignBin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "invalid chironym campaign: evaluate failed: %v\n", err)
		return 1
	}

	epoch := 1
	varDir := "/app/var"
	if sb, err := os.ReadFile(filepath.Join(varDir, "chironym_state.json")); err == nil {
		var prev publish.State
		if json.Unmarshal(sb, &prev) == nil {
			epoch = prev.Epoch + 1
		}
	}

	bd := riskgate.BundleDigest(pd, pold, res.EmbedDigest, res.Threshold, res.Temperature)
	rows := make([]publish.UttRow, 0, len(res.Rows))
	sort.Slice(res.Rows, func(i, j int) bool { return res.Rows[i].Utt.UttID < res.Rows[j].Utt.UttID })
	for _, r := range res.Rows {
		rows = append(rows, publish.UttRow{
			UttID: r.Utt.UttID, Fold: r.Utt.Fold, Score: r.Score, Conf: r.Conf, Accepted: r.Accept, Y: r.Y,
		})
	}
	rep := publish.Report{
		SchemaRev: 1, CampaignID: pack.CampaignID,
		PackDigest: pd, PolicyDigest: pold, EmbedDigest: res.EmbedDigest, BundleDigest: bd,
		Temperature: res.Temperature, Threshold: res.Threshold,
		CalibCoverage: res.CalibCov, CalibRisk: res.CalibRisk,
		EvalCoverage: res.EvalCov, EvalRisk: res.EvalRisk,
		Utterances: rows,
	}
	st := publish.State{
		SchemaRev: 1, CampaignID: pack.CampaignID, Epoch: epoch,
		PackDigest: pd, PolicyDigest: pold, EmbedDigest: res.EmbedDigest, BundleDigest: bd,
		Temperature: res.Temperature, Threshold: res.Threshold,
		EvalCoverage: res.EvalCov, EvalRisk: res.EvalRisk,
	}
	hist := publish.Hist{
		Epoch: epoch, CampaignID: pack.CampaignID, BundleDigest: bd,
		Temperature: res.Temperature, Threshold: res.Threshold,
		EvalCoverage: res.EvalCov, EvalRisk: res.EvalRisk, Status: "ok",
	}
	if err := publish.WriteAll(out, varDir, rep, st, hist); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if err := ledger.Append(varDir, ledger.Entry{
		CampaignID: pack.CampaignID, BundleDigest: bd, Epoch: epoch, Status: "ok",
	}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Printf("TOP_ACCEPT_RATE=%.6f\n", res.EvalCov)
	fmt.Printf("BUNDLE_DIGEST=%s\n", bd)
	fmt.Printf("EPOCH=%d\n", epoch)
	return 0
}

func flagVal(args []string, name string) string {
	for i := 0; i+1 < len(args); i++ {
		if args[i] == name {
			return args[i+1]
		}
	}
	return ""
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
