package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"time"

	"orbit.local/sentinel/internal/certify"
)

type options struct {
	dbPath, apiOrigin, publishDir string
	timeout                       time.Duration
}

func parse(arguments []string) (options, error) {
	flags := flag.NewFlagSet("orbit-certify", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	db := flags.String("db", "", "SQLite registry path")
	api := flags.String("api", "", "sample API origin")
	publish := flags.String("publish-dir", "", "publication directory")
	timeoutMS := flags.Int("timeout-ms", 5000, "HTTP timeout")
	if err := flags.Parse(arguments); err != nil {
		return options{}, errors.New("invalid arguments")
	}
	if flags.NArg() != 0 || *db == "" || *api == "" || *publish == "" {
		return options{}, errors.New("--db, --api, and --publish-dir are required")
	}
	if !filepath.IsAbs(*db) || !filepath.IsAbs(*publish) {
		return options{}, errors.New("database and publication paths must be absolute")
	}
	parsed, err := url.Parse(*api)
	if err != nil || parsed.Scheme != "http" || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || (parsed.Path != "" && parsed.Path != "/") {
		return options{}, errors.New("--api must be a plain HTTP origin")
	}
	if *timeoutMS <= 0 {
		return options{}, errors.New("--timeout-ms must be positive")
	}
	return options{dbPath: *db, apiOrigin: parsed.String(), publishDir: *publish, timeout: time.Duration(*timeoutMS) * time.Millisecond}, nil
}
func main() {
	opts, err := parse(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	ctx, cancel := context.WithTimeout(context.Background(), opts.timeout*time.Duration(200))
	defer cancel()
	if _, err = certify.Run(ctx, opts.dbPath, opts.apiOrigin, opts.publishDir, opts.timeout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(3)
	}
}
