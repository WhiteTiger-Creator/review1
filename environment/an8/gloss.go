package an8

import "fmt"

// GlossView pretty-prints view tuples without modular fold.
func GlossView(bearing float64) string {
	return fmt.Sprintf("(%0.2f)", bearing)
}
