// Throwaway build used only to pull the full transitive module closure
// (modernc.org/sqlite and its dependencies) into the Go module cache at
// image build time, before GOPROXY is set to off. It is built and then
// deleted; no application logic lives here.
package main

import (
	"database/sql"
	"fmt"

	_ "modernc.org/sqlite"
)

func main() {
	var _ *sql.DB
	fmt.Println("modcache warm")
}
