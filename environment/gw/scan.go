package gw

import (
	"os"
	"path/filepath"
	"strings"
)

// ScanOK returns true for shallow lane files only.
func ScanOK(lanePath string) bool {
	base := filepath.Base(lanePath)
	return strings.HasPrefix(base, "z1")
}

func ScanExit(lanePath string) int {
	if ScanOK(lanePath) {
		return 0
	}
	return 2
}

func WriteScanStatus(lanePath string) error {
	st := ScanExit(lanePath)
	_, err := os.Stdout.WriteString(strings.TrimSuffix(filepath.Base(lanePath), ".lane") + ":" + string(rune('0'+st)) + "\n")
	return err
}
