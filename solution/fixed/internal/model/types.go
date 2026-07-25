// Package model holds the core data types shared across the privileged helper
// dispatcher, together with the canonical filesystem layout under /app.
package model

import (
	"os"
	"path/filepath"
	"strings"
)

// Request is the only structure a caller may submit. Every field is mandatory
// and must be free of NUL bytes. Unknown JSON fields are rejected by the
// canonical decoder.
type Request struct {
	RequestID string `json:"request_id"`
	Principal string `json:"principal"`
	Action    string `json:"action"`
	Unit      string `json:"unit"`
}

// Binding is the authenticated context passed to a helper. A helper reply must
// echo these values exactly; a mismatch is treated as a denial.
type Binding struct {
	RequestDigest      string `json:"request_digest"`
	ManifestGeneration int    `json:"manifest_generation"`
	ManifestDigest     string `json:"manifest_digest"`
}

// HelperReply is the message emitted by a privileged helper on stdout. The
// dispatcher never lets a reply grant authority; it is only used to confirm the
// effect that authorization already permitted. The Decision field is decoded so
// that it can be explicitly ignored.
type HelperReply struct {
	Status             string `json:"status"`
	RequestDigest      string `json:"request_digest"`
	ManifestGeneration int    `json:"manifest_generation"`
	ManifestDigest     string `json:"manifest_digest"`
	Action             string `json:"action"`
	Unit               string `json:"unit"`
	Effect             string `json:"effect"`
	// Decision is intentionally captured and then discarded: a helper can never
	// upgrade or downgrade the dispatcher decision.
	Decision string `json:"decision"`
}

// HelperEntry describes a single privileged helper inside the signed manifest.
type HelperEntry struct {
	RelativePath string `json:"relative_path"`
	SHA256       string `json:"sha256"`
	Interpreter  string `json:"interpreter"`
	Effect       string `json:"effect"`
}

// Manifest is the signed authority document.
type Manifest struct {
	Scenario   string                 `json:"scenario"`
	Generation int                    `json:"generation"`
	Policy     map[string][]string    `json:"policy"`
	Helpers    map[string]HelperEntry `json:"helpers"`
}

// LoadedManifest bundles a verified manifest with the digest of its exact file
// bytes.
type LoadedManifest struct {
	Manifest Manifest
	Digest   string
	Bytes    []byte
}

// LaunchSurface identifies how a dispatch was initiated.
type (
	LaunchSurface = string
)

const (
	LaunchDirect = "direct"
	LaunchJob    = "job"
)

// Decision outcomes.
const (
	DecisionAllow    = "allow"
	DecisionDeny     = "deny"
	DecisionConflict = "conflict"

	OutcomeNone = "none"
)

// ActionToHelper maps a request action to its helper name. Actions use
// underscores (seal_unit); helper names use hyphens (seal-unit).
func ActionToHelper(action string) string {
	return strings.ReplaceAll(action, "_", "-")
}

// Paths captures every hardcoded location the dispatcher relies on, rooted at
// /app by default. The PRIVHELPER_ROOT environment variable may relocate the
// root, which is used by the security self-test to run against an isolated
// tree.
type Paths struct {
	Root string
}

// NewPaths resolves the active filesystem layout, honoring PRIVHELPER_ROOT.
func NewPaths() Paths {
	root := os.Getenv("PRIVHELPER_ROOT")
	if root == "" {
		root = "/app"
	}
	return Paths{Root: root}
}

func (p Paths) VarDir() string   { return filepath.Join(p.Root, "var", "privhelper") }
func (p Paths) EtcDir() string   { return filepath.Join(p.Root, "etc", "privhelper") }
func (p Paths) Manifest() string { return filepath.Join(p.VarDir(), "authority-manifest.json") }
func (p Paths) Signature() string {
	return filepath.Join(p.VarDir(), "authority-manifest.sig")
}
func (p Paths) PublicKey() string { return filepath.Join(p.EtcDir(), "authority.pub") }
func (p Paths) Journal() string   { return filepath.Join(p.VarDir(), "journal.jsonl") }
func (p Paths) Decisions() string { return filepath.Join(p.VarDir(), "decisions.jsonl") }
func (p Paths) Effects() string   { return filepath.Join(p.VarDir(), "effects.jsonl") }
func (p Paths) State() string     { return filepath.Join(p.VarDir(), "state.json") }
func (p Paths) Libexec() string   { return filepath.Join(p.Root, "libexec", "privhelper") }
func (p Paths) CallerBin() string { return filepath.Join(p.Root, "var", "caller-bin") }
func (p Paths) Share() string     { return filepath.Join(p.Root, "share", "privhelper") }
func (p Paths) ShareHelpers() string {
	return filepath.Join(p.Share(), "helpers")
}
func (p Paths) ShareManifest() string {
	return filepath.Join(p.Share(), "authority-manifest-v1.json")
}
func (p Paths) ShareSignature() string {
	return filepath.Join(p.Share(), "authority-manifest-v1.sig")
}
func (p Paths) ShareCallerBin() string {
	return filepath.Join(p.Share(), "caller-bin")
}
func (p Paths) ShareCallerPython() string {
	return filepath.Join(p.Share(), "caller-python")
}
func (p Paths) CallerPython() string {
	return filepath.Join(p.Root, "var", "caller-python")
}
func (p Paths) Reports() string { return filepath.Join(p.Root, "reports") }
