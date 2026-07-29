package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	"raidscrubctl/internal/campaign"
	"raidscrubctl/internal/model"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: raidscrubctl apply|model-digest|self-test")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "self-test":
		fmt.Println("raidscrubctl-v2")
	case "model-digest":
		fmt.Println(model.Digest())
	case "apply":
		opt := campaign.Options{
			Root:      env("RAID_ROOT", "/app/work/raid-root"),
			Output:    env("RAID_OUTPUT", "/app/output"),
			Threshold: 10,
			Campaign:  "standard",
			Epoch:     "1",
		}
		args := os.Args[2:]
		for i := 0; i < len(args); i++ {
			arg := args[i]
			name := arg
			inline := ""
			hasInline := false
			if eq := strings.Index(arg, "="); eq > 0 {
				name = arg[:eq]
				inline = arg[eq+1:]
				hasInline = true
			}
			value := func() string {
				if hasInline {
					return inline
				}
				if i+1 < len(args) {
					i++
					return args[i]
				}
				return ""
			}
			switch name {
			case "--threshold":
				if v, err := strconv.Atoi(value()); err == nil {
					opt.Threshold = v
				}
			case "--campaign":
				opt.Campaign = value()
			case "--epoch":
				opt.Epoch = value()
			case "--urgent":
				opt.Urgent = value()
			case "--root":
				opt.Root = value()
			case "--output":
				opt.Output = value()
			case "--read-error":
				opt.ReadError = true
			case "--corrupt-checkpoint":
				opt.CorruptCheckpoint = true
			default:
				fmt.Fprintf(os.Stderr, "ignoring unknown flag: %s\n", name)
			}
		}
		res, err := campaign.Run(opt)
		if err != nil {
			fmt.Fprintf(os.Stderr, "apply failed: %v\n", err)
			os.Exit(1)
		}
		if res.Report.Accepted {
			fmt.Println("accepted=true")
			os.Exit(0)
		}
		fmt.Println("accepted=false")
		os.Exit(0)
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", os.Args[1])
		os.Exit(2)
	}
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
