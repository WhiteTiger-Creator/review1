package helper

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"privhelper/internal/model"
)

// Resolution is the outcome of resolving a helper by name.
type Resolution struct {
	Name    string
	Path    string
	Digest  string
	Trusted bool
	Content []byte
	Entry   model.HelperEntry
	Reason  string
}

// Resolve locates a helper by name and returns its resolution details.
func Resolve(p model.Paths, m model.Manifest, name string) Resolution {
	res := Resolution{Name: name}

	entry, ok := m.Helpers[name]
	if !ok {
		res.Reason = "helper_not_in_manifest"
		return res
	}
	res.Entry = entry

	candidates := make([]string, 0, 4)
	if hp := os.Getenv("HELPER_PATH"); hp != "" {
		candidates = append(candidates, filepath.Join(hp, name))
	}
	if found, err := exec.LookPath(name); err == nil {
		candidates = append(candidates, found)
	}
	base := filepath.Clean(p.Libexec())
	candidates = append(candidates, filepath.Join(base, entry.RelativePath))

	for _, candidate := range candidates {
		info, err := os.Stat(candidate)
		if err != nil || info.IsDir() {
			continue
		}
		content, err := os.ReadFile(candidate)
		if err != nil {
			continue
		}
		sum := sha256.Sum256(content)
		digest := hex.EncodeToString(sum[:])
		res.Path = candidate
		res.Digest = digest
		res.Content = content
		res.Trusted = digest == entry.SHA256
		if res.Trusted {
			res.Reason = "trusted"
		} else {
			res.Reason = "digest_or_path_mismatch"
		}
		return res
	}

	res.Reason = "helper_missing"
	return res
}

// ResolveByAction resolves the helper responsible for the given action.
func ResolveByAction(p model.Paths, m model.Manifest, action string) Resolution {
	return Resolve(p, m, model.ActionToHelper(action))
}

func Errorf(format string, args ...any) error {
	return fmt.Errorf(format, args...)
}
