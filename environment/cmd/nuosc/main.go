package main

import (
	"flag"
	"fmt"
	"os"

	"earth-neutrino-propagation/internal/simulation"
)

func main() {
	config := flag.String("config", "/app/fixtures/earth_medium.json", "propagation configuration")
	propagation := flag.String("propagation", "/app/output/propagation.json", "propagation output")
	continuation := flag.String("continuation", "/app/output/continuation.json", "continuation output")
	reproducibility := flag.String("reproducibility", "/app/output/reproducibility.json", "reproducibility output")
	resume := flag.String("resume", "", "continuation to resume")
	stopAfter := flag.Int("stop-after", -1, "total number of physical layers to complete")
	stopAfterSteps := flag.Int("stop-after-steps", -1, "total number of numerical substeps to complete")
	flag.Parse()
	if flag.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "unexpected positional arguments")
		os.Exit(2)
	}
	if err := simulation.Run(simulation.Options{ConfigPath: *config, PropagationPath: *propagation, ContinuationPath: *continuation, ReproducibilityPath: *reproducibility, ResumePath: *resume, StopAfterLayers: *stopAfter, StopAfterSteps: *stopAfterSteps}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
