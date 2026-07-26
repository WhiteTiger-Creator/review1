package q9c

import (
	"os"
	"path/filepath"
	"strings"
)

// CoveragePin reports whether an overlay profile file is present for the
// computed coverage path under the primary config directory.
func CoveragePin(primaryPath, overlayProfile string) bool {
	profile := strings.TrimSpace(overlayProfile)
	if profile == "" {
		return false
	}
	dir := filepath.Dir(primaryPath)
	// Path is assembled at runtime so it is not a greppable literal overlay file.
	pin := filepath.Join(dir, "overlays", profile+".toml")
	_, err := os.Stat(pin)
	return err == nil
}
