package main

import (
	"fmt"

	"example.com/lib/bind"
	"example.com/lib/legacy/v2"
	"example.com/lib/root"
)

func main() {
	fmt.Println(root.Tag(), bind.Tag(), legacy.Tag(), cue())
}
