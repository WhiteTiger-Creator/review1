package clientord

import (
	"strconv"
	"strings"
	"unicode"
)

// Specificity returns the client specificity score used for grant ordering.
func Specificity(clientID string) int {
	for _, r := range clientID {
		if unicode.IsLetter(r) {
			return 128
		}
	}
	if i := strings.LastIndex(clientID, "/"); i >= 0 {
		p, err := strconv.Atoi(clientID[i+1:])
		if err == nil {
			return p
		}
	}
	return 32
}
