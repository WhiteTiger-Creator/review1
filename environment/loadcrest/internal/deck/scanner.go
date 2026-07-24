package deck

import (
	"bufio"
	"fmt"
	"io"
	"math"
	"strconv"
	"strings"
	"unicode"
)

// ScanLines yields non-comment, non-blank logical lines with 1-based original numbers.
func ScanLines(r io.Reader) ([]string, error) {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	out := make([]string, 0, 64)
	for sc.Scan() {
		line := sc.Text()
		trim := strings.TrimLeftFunc(line, unicode.IsSpace)
		if trim == "" || strings.HasPrefix(trim, "#") {
			continue
		}
		out = append(out, strings.TrimSpace(line))
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// Tokens splits on ASCII spaces and tabs.
func Tokens(line string) []string {
	return strings.FieldsFunc(line, func(r rune) bool {
		return r == ' ' || r == '\t'
	})
}

// ParseFloat requires a finite float64.
func ParseFloat(tok string) (float64, error) {
	v, err := strconv.ParseFloat(tok, 64)
	if err != nil {
		return 0, err
	}
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return 0, fmt.Errorf("non-finite number %q", tok)
	}
	return v, nil
}

// ValidID checks POWER-01 / TRACE-01 identifier grammar.
func ValidID(id string) bool {
	if len(id) < 1 || len(id) > 48 {
		return false
	}
	for i, r := range id {
		ok := (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '.' || r == '_' || r == '-'
		if !ok {
			return false
		}
		if i == 0 && !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
			return false
		}
	}
	return true
}

// FormatFloat is shortest round-trip finite formatting with negative zero collapsed.
func FormatFloat(v float64) string {
	if v == 0 {
		return "0"
	}
	return strconv.FormatFloat(v, 'g', -1, 64)
}
