package main

import (
	"flag"
	"fmt"
	"os"

	"banditeva/evalcfg"
	"banditeva/h8s"
	"banditeva/hparams"
	"banditeva/j3f"
	"banditeva/k4m"
	"banditeva/n7w"
	"banditeva/p5r"
)

func main() {
	dataDir := flag.String("data", "/app/data", "logged bandit interaction snapshots")
	featuresDir := flag.String("features", "/app/features", "action schema directory")
	modelsDir := flag.String("models", "/app/models", "target policy and reward model")
	cfgPath := flag.String("config", "/app/config/eval.json", "offline evaluation hyperparameters")
	outDir := flag.String("out", "/app/output", "directory for ips_eval.json")
	flag.Parse()

	rt, err := evalcfg.Load(*cfgPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "evalcfg: %v\n", err)
		os.Exit(1)
	}
	bundle, err := k4m.LoadExport(*dataDir, *featuresDir, *modelsDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "load: %v\n", err)
		os.Exit(1)
	}

	clipMax := hparams.ClipMax
	if rt.ClipMax > 0 {
		clipMax = rt.ClipMax
	}
	floor := hparams.PropensityFloor
	if rt.PropensityFloor > 0 {
		floor = rt.PropensityFloor
	}
	essThr := hparams.ESSThreshold
	if rt.ESSThreshold > 0 {
		essThr = rt.ESSThreshold
	}
	ciThr := hparams.CIThreshold
	if rt.CIThreshold > 0 {
		ciThr = rt.CIThreshold
	}
	valueFloor := hparams.ValueFloor
	if rt.ValueFloor > 0 {
		valueFloor = rt.ValueFloor
	}

	win := n7w.ApplyWindow(bundle, rt.CutoffUnix, rt.EvalWindowSec, floor)
	weighted := j3f.WeightAll(win.Events, bundle.Target, bundle.RewardModel, bundle.Actions, clipMax)
	est := h8s.Evaluate(weighted, bundle.Actions, clipMax, essThr, ciThr, valueFloor)

	rep := p5r.Build(rt, win, est, clipMax, floor, essThr, ciThr, valueFloor)
	rep = p5r.Finalize(rep, *cfgPath, rt)
	if err := p5r.WriteJSON(*outDir, rep); err != nil {
		fmt.Fprintf(os.Stderr, "emit: %v\n", err)
		os.Exit(1)
	}
}
