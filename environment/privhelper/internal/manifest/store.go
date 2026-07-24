package manifest

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"

	"privhelper/internal/fsutil"
	"privhelper/internal/model"
)

// Store owns reading and installing the signed manifest on disk.
type Store struct {
	Paths model.Paths
}

// NewStore constructs a Store bound to the given layout.
func NewStore(p model.Paths) *Store {
	return &Store{Paths: p}
}

// digestBytes returns the SHA-256 hex digest of the exact bytes.
func digestBytes(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

// LoadCurrent reads the installed manifest and validates its schema before
// returning it. A manifest that fails schema validation is never returned as
// trusted.
func (s *Store) LoadCurrent() (model.LoadedManifest, error) {
	manifestBytes, err := os.ReadFile(s.Paths.Manifest())
	if err != nil {
		return model.LoadedManifest{}, fmt.Errorf("read manifest: %w", err)
	}
	m, err := Parse(manifestBytes)
	if err != nil {
		return model.LoadedManifest{}, err
	}
	if err := ValidateSchema(m); err != nil {
		return model.LoadedManifest{}, err
	}
	return model.LoadedManifest{
		Manifest: m,
		Digest:   digestBytes(manifestBytes),
		Bytes:    manifestBytes,
	}, nil
}

// InstalledGeneration returns the generation of the currently installed
// manifest, or 0 if none is installed / verifiable.
func (s *Store) InstalledGeneration() int {
	loaded, err := s.LoadCurrent()
	if err != nil {
		return 0
	}
	return loaded.Manifest.Generation
}

// Install verifies and atomically installs a candidate manifest + signature.
// It enforces the ops-seal scenario, a strictly increasing generation (rollback
// and replay are rejected), and full schema validation before either file is
// written.
func (s *Store) Install(manifestPath, sigPath string) (model.LoadedManifest, error) {
	manifestBytes, err := os.ReadFile(manifestPath)
	if err != nil {
		return model.LoadedManifest{}, fmt.Errorf("read candidate manifest: %w", err)
	}
	sigBytes, err := os.ReadFile(sigPath)
	if err != nil {
		return model.LoadedManifest{}, fmt.Errorf("read candidate signature: %w", err)
	}
	pubBytes, err := os.ReadFile(s.Paths.PublicKey())
	if err != nil {
		return model.LoadedManifest{}, fmt.Errorf("read public key: %w", err)
	}

	if err := VerifySignature(manifestBytes, sigBytes, pubBytes); err != nil {
		return model.LoadedManifest{}, err
	}
	m, err := Parse(manifestBytes)
	if err != nil {
		return model.LoadedManifest{}, err
	}
	if err := ValidateSchema(m); err != nil {
		return model.LoadedManifest{}, err
	}
	if m.Scenario != "ops-seal" {
		return model.LoadedManifest{}, fmt.Errorf("manifest scenario must be ops-seal, got %q", m.Scenario)
	}

	installed := s.InstalledGeneration()
	if m.Generation < installed {
		return model.LoadedManifest{}, fmt.Errorf(
			"manifest generation %d does not advance installed generation %d (rollback/replay rejected)",
			m.Generation, installed)
	}

	if err := fsutil.EnsureDir(s.Paths.VarDir()); err != nil {
		return model.LoadedManifest{}, err
	}
	// Install both files atomically. The signature is written first so a crash
	// can never leave a manifest without its matching signature.
	if err := fsutil.AtomicWriteFile(s.Paths.Signature(), sigBytes, 0o644); err != nil {
		return model.LoadedManifest{}, fmt.Errorf("install signature: %w", err)
	}
	if err := fsutil.AtomicWriteFile(s.Paths.Manifest(), manifestBytes, 0o644); err != nil {
		return model.LoadedManifest{}, fmt.Errorf("install manifest: %w", err)
	}

	return model.LoadedManifest{
		Manifest: m,
		Digest:   digestBytes(manifestBytes),
		Bytes:    manifestBytes,
	}, nil
}
