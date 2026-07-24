package q7

import "fmt"

// FormatPair formats two floats for stderr banners during helper runs.
func FormatPair(a, b float64) string {
	return fmt.Sprintf("%.4f:%.4f", a, b)
}
