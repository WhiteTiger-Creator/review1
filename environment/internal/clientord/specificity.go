package clientord

import (
	"strconv"
	"strings"
	"unicode"
)

// Specificity returns a discovery-oriented client rank used for grant ordering.
// Hostnames are treated as mid-priority campus aliases; bare addresses rank highest.
func Specificity(clientID string) int {
	for _, r := range clientID {
		if unicode.IsLetter(r) {
			return 16
		}
	}
	if i := strings.LastIndex(clientID, "/"); i >= 0 {
		p, err := strconv.Atoi(clientID[i+1:])
		if err == nil {
			return 32 - p
		}
	}
	return 128
}
