package engine

import (
	"flag"
	"fmt"
)

type options struct{ units, state, clock, output string }
type discard struct{}

func (discard) Write(data []byte) (int, error) { return len(data), nil }
func parse(args []string) (options, error) {
	var result options
	if len(args) == 0 || args[0] != "reconcile" {
		return result, fmt.Errorf("reconcile subcommand required")
	}
	set := flag.NewFlagSet("reconcile", flag.ContinueOnError)
	set.SetOutput(discard{})
	set.StringVar(&result.units, "units", "", "")
	set.StringVar(&result.state, "state", "", "")
	set.StringVar(&result.clock, "clock", "", "")
	set.StringVar(&result.output, "output", "", "")
	if err := set.Parse(args[1:]); err != nil || set.NArg() != 0 || result.units == "" || result.state == "" || result.clock == "" || result.output == "" {
		return result, fmt.Errorf("--units, --state, --clock, and --output are required")
	}
	return result, nil
}
