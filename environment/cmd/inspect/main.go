package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"gwc/sense"
)

func main() {
	pinned := flag.Int("pinned", 0, "pinned uid")
	current := flag.Int("current", 0, "current uid")
	flag.Parse()
	skew := sense.Skew(sense.Pair{Pinned: int32(*pinned), Current: int32(*current)})
	out := map[string]int{"cred_gap": skew}
	raw, _ := json.Marshal(out)
	fmt.Println(string(raw))
	_ = os.Stdout.Sync()
}
