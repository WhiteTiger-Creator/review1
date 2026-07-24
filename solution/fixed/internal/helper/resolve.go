// Package helper resolves and executes privileged helpers. Resolution is
// deliberately hostile to caller influence: only the manifest-declared artifact
// under /app/libexec/privhelper is ever considered, and PATH, HELPER_PATH and
// the current working directory are ignored entirely.
package helper

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"

	"privhelper/internal/model"
)

// Resolution is the outcome of resolving a helper by name.
type Resolution struct {
	Name    string
	Path    string
	Digest  string
	Trusted bool
	// Content holds the exact verified bytes. Execution uses these bytes; the
	// path is never reopened after verification.
	Content []byte
	Entry   model.HelperEntry
	// Reason explains an untrusted / failed resolution.
	Reason string
}

// Resolve locates the helper for the given name strictly under the libexec
// directory, using the manifest's relative_path. It rejects symlinks, non
// regular files, and group/world writable files, then compares the live digest
// against the manifest. The returned Resolution reports Trusted only when every
// check passes and the digest matches exactly.
func Resolve(p model.Paths, m model.Manifest, name string) Resolution {
	res := Resolution{Name: name}

	entry, ok := m.Helpers[name]
	if !ok {
		res.Reason = "helper_not_in_manifest"
		return res
	}
	res.Entry = entry

	// Only ever resolve under libexec + the manifest relative_path. The
	// relative_path has already been validated to be a single filename, but we
	// re-check that the joined path stays within libexec as defense in depth.
	base := filepath.Clean(p.Libexec())
	candidate := filepath.Join(base, entry.RelativePath)
	if filepath.Dir(candidate) != base {
		res.Reason = "helper_path_escapes_libexec"
		return res
	}
	res.Path = candidate

	info, err := os.Lstat(candidate)
	if err != nil {
		res.Reason = "helper_missing"
		return res
	}
	if info.Mode()&os.ModeSymlink != 0 {
		res.Reason = "helper_is_symlink"
		return res
	}
	if !info.Mode().IsRegular() {
		res.Reason = "helper_not_regular_file"
		return res
	}
	if info.Mode().Perm()&0o022 != 0 {
		res.Reason = "helper_group_or_world_writable"
		return res
	}

	content, err := os.ReadFile(candidate)
	if err != nil {
		res.Reason = "helper_unreadable"
		return res
	}
	sum := sha256.Sum256(content)
	res.Digest = hex.EncodeToString(sum[:])

	if res.Digest != entry.SHA256 {
		res.Reason = "helper_digest_mismatch"
		return res
	}

	res.Content = content
	res.Trusted = true
	res.Reason = "trusted"
	return res
}

// ResolveByAction resolves the helper responsible for the given action.
func ResolveByAction(p model.Paths, m model.Manifest, action string) Resolution {
	return Resolve(p, m, model.ActionToHelper(action))
}

// Errorf is a small helper so callers can build resolution errors uniformly.
func Errorf(format string, args ...any) error {
	return fmt.Errorf(format, args...)
}
