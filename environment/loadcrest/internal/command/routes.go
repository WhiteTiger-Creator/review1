package command

import (
	"fmt"
	"os"
	"strings"

	"loadcrest/internal/arc"
	"loadcrest/internal/deck"
	"loadcrest/internal/decoy"
	"loadcrest/internal/diagnostic"
	"loadcrest/internal/grid"
	"loadcrest/internal/record"
)

// Run dispatches admittance or trace.
func Run(args Args) int {
	switch args.Mode {
	case "help":
		WriteHelp()
		return 0
	case "admittance":
		return runAdmittance(args.Network)
	case "trace":
		return runTrace(args.Network, args.Ramp, args.Map)
	default:
		return diagnostic.Emit(diagnostic.EPath, "unknown mode")
	}
}

func runAdmittance(networkPath string) int {
	net, err := deck.LoadNetwork(networkPath)
	if err != nil {
		if os.IsNotExist(err) || strings.Contains(err.Error(), "absolute") || strings.Contains(err.Error(), "cannot read") {
			return diagnostic.Emit(diagnostic.EPath, err.Error())
		}
		return diagnostic.Emit(diagnostic.ENetworkDeck, err.Error())
	}
	buses := grid.BusesFromDeck(net)
	branches := grid.BranchesFromDeck(net)
	if err := grid.ValidateEnergizedIsland(buses, branches, net.SlackID()); err != nil {
		return diagnostic.Emit(diagnostic.EIsland, err.Error())
	}
	out, err := decoy.RunAdmittance(net)
	if err != nil {
		return diagnostic.Emit(diagnostic.EIsland, err.Error())
	}
	os.Stdout.Write(out)
	return 0
}

func runTrace(networkPath, rampPath, mapPath string) int {
	record.RemovePrivateSibling(mapPath)
	net, err := deck.LoadNetwork(networkPath)
	if err != nil {
		if os.IsNotExist(err) || strings.Contains(err.Error(), "absolute") || strings.Contains(err.Error(), "cannot read") {
			return diagnostic.Emit(diagnostic.EPath, err.Error())
		}
		return diagnostic.Emit(diagnostic.ENetworkDeck, err.Error())
	}
	buses := grid.BusesFromDeck(net)
	branches := grid.BranchesFromDeck(net)
	if err := grid.ValidateEnergizedIsland(buses, branches, net.SlackID()); err != nil {
		return diagnostic.Emit(diagnostic.EIsland, err.Error())
	}
	ramp, err := deck.LoadRamp(rampPath, net)
	if err != nil {
		if os.IsNotExist(err) || strings.Contains(err.Error(), "absolute") || strings.Contains(err.Error(), "cannot read") {
			return diagnostic.Emit(diagnostic.EPath, err.Error())
		}
		return diagnostic.Emit(diagnostic.EContinuation, err.Error())
	}
	out, err := arc.RunContinuation(net, ramp)
	if err != nil {
		record.RemovePrivateSibling(mapPath)
		msg := err.Error()
		switch {
		case strings.Contains(msg, "base_reactive"):
			return diagnostic.Emit(diagnostic.EBaseReactiveLimit, msg)
		case strings.Contains(msg, "basepoint"):
			return diagnostic.Emit(diagnostic.EBasepoint, msg)
		case strings.Contains(msg, "reactive"):
			return diagnostic.Emit(diagnostic.EReactiveEvent, msg)
		case strings.Contains(msg, "fold"):
			return diagnostic.Emit(diagnostic.EFold, msg)
		case strings.Contains(msg, "island"):
			return diagnostic.Emit(diagnostic.EIsland, msg)
		default:
			return diagnostic.Emit(diagnostic.EContinuation, msg)
		}
	}
	if err := record.WriteMap(mapPath, out.Manifest, out.Curve, out.Events, out.CriticalBuses, out.CriticalBranch); err != nil {
		record.RemovePrivateSibling(mapPath)
		return diagnostic.Emit(diagnostic.EMap, err.Error())
	}
	fmt.Fprintf(os.Stdout, "FOLD_MAPPED %s %s %s %s\n",
		mapPath,
		deck.FormatFloat(out.CriticalLambda),
		out.Manifest.NetworkSHA256,
		out.Manifest.RampSHA256,
	)
	return 0
}
