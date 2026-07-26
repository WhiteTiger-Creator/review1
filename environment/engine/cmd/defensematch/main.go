package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"signal-defense/internal/integrity"
	"signal-defense/internal/match"
	"signal-defense/internal/replay"
)

func main() {
	assetRoot := flag.String("assets", "/opt/signal-defense", "protected match root")
	scenarioPath := flag.String("scenario", "", "scenario JSON path")
	scenarioName := flag.String("scenario-name", "", "public scenario name under waves/")
	botDir := flag.String("bot", "/app/work/defensebot", "bot module directory")
	output := flag.String("output", "/app/output", "output root")
	doctrine := flag.String("doctrine", "", "override partner doctrine")
	seed := flag.Int64("seed", -1, "override seed")
	inject := flag.String("inject-failure", "", "write|validate|rename|pointer|compile|protocol")
	dumpJSON := flag.Bool("print-summary", false, "print summary JSON to stdout")
	skipVerify := flag.Bool("skip-verify", false, "skip sealed campaign verification (tests only)")
	buildManifest := flag.Bool("build-manifest", false, "rebuild sealed campaign manifest")
	flag.Parse()

	if *buildManifest {
		paths, err := integrity.CollectRelPaths(*assetRoot, "contracts/", "grids/", "waves/", "partners/")
		if err != nil {
			fmt.Fprintf(os.Stderr, "manifest: %v\n", err)
			os.Exit(2)
		}
		man, err := integrity.BuildManifest(*assetRoot, paths)
		if err != nil {
			fmt.Fprintf(os.Stderr, "manifest: %v\n", err)
			os.Exit(2)
		}
		if err := os.MkdirAll(filepath.Join(*assetRoot, "integrity"), 0o755); err != nil {
			fmt.Fprintf(os.Stderr, "manifest: %v\n", err)
			os.Exit(2)
		}
		if err := integrity.WriteManifest(filepath.Join(*assetRoot, "integrity", "manifest.json"), man); err != nil {
			fmt.Fprintf(os.Stderr, "manifest: %v\n", err)
			os.Exit(2)
		}
		fmt.Println("manifest written")
		return
	}

	if !*skipVerify {
		if err := match.VerifyAssets(*assetRoot); err != nil {
			fmt.Fprintf(os.Stderr, "integrity: %v\n", err)
			os.Exit(2)
		}
	}

	var sc match.Scenario
	var err error
	switch {
	case *scenarioPath != "":
		sc, err = match.LoadScenarioFile(*scenarioPath)
	case *scenarioName != "":
		path := filepath.Join(*assetRoot, "waves", *scenarioName+".json")
		sc, err = match.LoadScenarioFile(path)
	default:
		fmt.Fprintln(os.Stderr, "scenario or scenario-name required")
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "scenario: %v\n", err)
		os.Exit(2)
	}
	if *doctrine != "" {
		sc.PartnerDoctrine = *doctrine
	}
	if *seed >= 0 {
		sc.Seed = *seed
	}

	cfg := match.Config{
		AssetRoot:  *assetRoot,
		Scenario:   sc,
		BotDir:     *botDir,
		OutputRoot: *output,
		InjectFail: *inject,
	}
	if *skipVerify {
		cfg.AssetRoot = ""
	}

	gen, err := match.Run(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "match failed: %v\n", err)
		if *inject != "" {
			if _, rerr := replay.ReadCurrent(*output); rerr == nil {
				fmt.Fprintln(os.Stderr, "previous generation preserved")
			}
		}
		os.Exit(1)
	}
	if *dumpJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(gen.Summary)
	}
}
