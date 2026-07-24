package command

import (
	"fmt"
	"os"
	"strings"
)

// Args holds parsed CLI arguments.
type Args struct {
	Mode    string
	Network string
	Ramp    string
	Map     string
}

// ParseArgs parses the public fold-map CLI.
func ParseArgs(argv []string) (Args, error) {
	if len(argv) == 0 {
		return Args{}, fmt.Errorf("missing mode")
	}
	mode := argv[0]
	if mode == "-h" || mode == "--help" || mode == "help" {
		return Args{Mode: "help"}, nil
	}
	a := Args{Mode: mode}
	rest := argv[1:]
	for i := 0; i < len(rest); i++ {
		switch rest[i] {
		case "--network":
			if i+1 >= len(rest) {
				return Args{}, fmt.Errorf("missing --network value")
			}
			a.Network = rest[i+1]
			i++
		case "--ramp":
			if i+1 >= len(rest) {
				return Args{}, fmt.Errorf("missing --ramp value")
			}
			a.Ramp = rest[i+1]
			i++
		case "--map":
			if i+1 >= len(rest) {
				return Args{}, fmt.Errorf("missing --map value")
			}
			a.Map = rest[i+1]
			i++
		default:
			return Args{}, fmt.Errorf("unknown argument %s", rest[i])
		}
	}
	switch mode {
	case "admittance":
		if a.Network == "" || a.Ramp != "" || a.Map != "" {
			return Args{}, fmt.Errorf("admittance requires only --network")
		}
	case "trace":
		if a.Network == "" || a.Ramp == "" || a.Map == "" {
			return Args{}, fmt.Errorf("trace requires --network --ramp --map")
		}
	default:
		return Args{}, fmt.Errorf("unknown mode %s", mode)
	}
	if a.Network != "" && !strings.HasPrefix(a.Network, "/") {
		return Args{}, fmt.Errorf("network path must be absolute")
	}
	if a.Ramp != "" && !strings.HasPrefix(a.Ramp, "/") {
		return Args{}, fmt.Errorf("ramp path must be absolute")
	}
	if a.Map != "" && !strings.HasPrefix(a.Map, "/") {
		return Args{}, fmt.Errorf("map path must be absolute")
	}
	return a, nil
}

// HelpText is the deterministic help banner.
func HelpText() string {
	return strings.TrimSpace(`
fold-map — AC voltage-collapse fold mapping

Usage:
  fold-map admittance --network /absolute/network.acn
  fold-map trace --network /absolute/network.acn --ramp /absolute/loading.rmp --map /absolute/result.vcm
`) + "\n"
}

// WriteHelp prints help to stdout.
func WriteHelp() {
	fmt.Fprint(os.Stdout, HelpText())
}
