package main

import (
	"fmt"
	"os"
	"path/filepath"

	"nfsacld/internal/exportacl"
	"nfsacld/internal/runtime"
	"nfsacld/internal/svcconf"
	"nfsacld/internal/walops"
)

func main() {
	cfgPath := "/app/config/exports.json"
	if len(os.Args) > 1 {
		cfgPath = os.Args[1]
	}

	conf, err := svcconf.Load(cfgPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "config: %v\n", err)
		os.Exit(1)
	}

	ops, err := walops.Load(conf.JournalPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "journal: %v\n", err)
		os.Exit(1)
	}

	toRun, applied, skipped := walops.FilterApplied(ops)
	mgr := exportacl.New(
		conf.MaxClientsPerExport,
		conf.DefaultSquash,
		conf.DefaultAnonUID,
		conf.DefaultAnonGID,
		conf.DefaultAccess,
		conf.RequireSecurePorts,
	)
	for _, op := range toRun {
		mgr.Apply(op)
	}

	// After journal replay, align manager capacity with the mounted site overlay
	// so final inventory labels match live regional policy.
	mgr.MaxClients = svcconf.OverlayMaxClients(filepath.Dir(cfgPath), conf.Profile)

	exports, wait := mgr.Snapshot()
	if err := runtime.Emit(
		conf.OutputDir,
		conf.ExportTableID,
		conf.EvaluationClock,
		conf.MaxClientsPerExport,
		exports,
		wait,
		applied,
		skipped,
		conf.Profile,
		cfgPath,
	); err != nil {
		fmt.Fprintf(os.Stderr, "persist: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Runtime NFS export ACL state persisted under %s\n", conf.OutputDir)
}
