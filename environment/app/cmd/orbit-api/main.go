package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"orbit.local/sentinel/internal/api"
)

func main() {
	flags := flag.NewFlagSet("orbit-api", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	db := flags.String("db", "", "SQLite registry path")
	publish := flags.String("publish-dir", "/app/out", "publication directory")
	web := flags.String("web", "/app/web", "dashboard directory")
	listen := flags.String("listen", "127.0.0.1:18080", "listen address")
	if err := flags.Parse(os.Args[1:]); err != nil || flags.NArg() != 0 || *db == "" || !filepath.IsAbs(*db) || !filepath.IsAbs(*publish) || !filepath.IsAbs(*web) {
		fmt.Fprintln(os.Stderr, "usage: orbit-api --db ABSOLUTE_PATH [--publish-dir ABSOLUTE_PATH] [--web ABSOLUTE_PATH] [--listen HOST:PORT]")
		os.Exit(2)
	}
	store, err := api.OpenStore(*db)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(3)
	}
	defer store.Close()
	if err = api.NewRouter(store, *publish, *web).Run(*listen); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(3)
	}
}
