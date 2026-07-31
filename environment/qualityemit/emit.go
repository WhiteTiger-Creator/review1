package qualityemit

import (
	"os"
	"path/filepath"
)

// WriteArtifact writes an emit-stage artifact under outDir.
func WriteArtifact(outDir, name string, body []byte) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(outDir, name), body, 0o644)
}
