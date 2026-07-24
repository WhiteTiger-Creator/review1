package main

import (
	"os"

	"loadcrest/internal/command"
	"loadcrest/internal/diagnostic"
)

func main() {
	if len(os.Args) < 2 {
		command.WriteHelp()
		os.Exit(diagnostic.Emit(diagnostic.EPath, "missing mode"))
	}
	args, err := command.ParseArgs(os.Args[1:])
	if err != nil {
		if args.Mode == "help" {
			command.WriteHelp()
			os.Exit(0)
		}
		os.Exit(diagnostic.Emit(diagnostic.EPath, err.Error()))
	}
	os.Exit(command.Run(args))
}
