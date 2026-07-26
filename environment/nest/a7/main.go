package main

import (
	"fmt"

	"example.com/lib/a7x"
	"example.com/lib/bind"
	"example.com/lib/legacy/v2"
	"example.com/lib/root"
)

func main() {
	fmt.Println(root.Tag(), bind.Tag(), a7x.Tag(), legacy.Tag())
}
