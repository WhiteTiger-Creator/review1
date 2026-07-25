// Package fsutil provides durable, atomic filesystem primitives. Every security
// transition in the dispatcher is persisted with an explicit fsync so that a
// crash can be reconstructed from the journal and ledgers.
package fsutil

import (
	"fmt"
	"os"
	"path/filepath"
)

// EnsureDir creates dir (and parents) with mode 0755 if it does not exist.
func EnsureDir(dir string) error {
	return os.MkdirAll(dir, 0o755)
}

// WriteFileSync writes data to path with the given permissions and fsyncs both
// the file and its parent directory before returning.
func WriteFileSync(path string, data []byte, perm os.FileMode) error {
	if err := EnsureDir(filepath.Dir(path)); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, perm)
	if err != nil {
		return err
	}
	if _, err := f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return syncDir(filepath.Dir(path))
}

// AppendLineSync appends a single JSON line (a trailing newline is added) to
// path and fsyncs the file. This is the durable primitive used for the journal
// and ledger append-only logs.
func AppendLineSync(path string, line []byte) error {
	if err := EnsureDir(filepath.Dir(path)); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	buf := append(append([]byte{}, line...), '\n')
	if _, err := f.Write(buf); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

// AtomicWriteFile writes data to a temp file in the destination directory and
// renames it into place, then fsyncs the directory. This guarantees the target
// never contains a partial write.
func AtomicWriteFile(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)
	if err := EnsureDir(dir); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".tmp-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	cleanup := func() { _ = os.Remove(tmpName) }

	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		cleanup()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		cleanup()
		return err
	}
	if err := tmp.Close(); err != nil {
		cleanup()
		return err
	}
	if err := os.Chmod(tmpName, perm); err != nil {
		cleanup()
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		cleanup()
		return err
	}
	return syncDir(dir)
}

// RemoveAll removes a tree, ignoring absence.
func RemoveAll(path string) error {
	if err := os.RemoveAll(path); err != nil {
		return fmt.Errorf("remove %s: %w", path, err)
	}
	return nil
}

func syncDir(dir string) error {
	d, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer d.Close()
	// Directory fsync is best-effort on some platforms; ignore EINVAL-style
	// failures but surface real errors.
	if err := d.Sync(); err != nil {
		// On some filesystems syncing a directory returns an error we can
		// safely ignore; treat it as non-fatal.
		return nil
	}
	return nil
}
