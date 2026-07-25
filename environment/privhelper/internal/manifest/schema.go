// Package manifest loads, verifies, validates, and installs the signed
// authority manifest that drives all dispatcher policy.
package manifest

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"privhelper/internal/model"
)

// KnownEffects is the closed set of effects a helper may declare.
var KnownEffects = map[string]bool{
	"unit_sealed":     true,
	"bundle_exported": true,
	"token_rotated":   true,
}

// AllowedInterpreter is the only interpreter a helper may be run under.
const AllowedInterpreter = "/usr/bin/python3"

var sha256Re = regexp.MustCompile(`^[0-9a-f]{64}$`)

// Parse decodes manifest bytes without applying schema validation. Unknown
// fields are rejected so a signed document cannot smuggle extra directives.
func Parse(data []byte) (model.Manifest, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var m model.Manifest
	if err := dec.Decode(&m); err != nil {
		return model.Manifest{}, fmt.Errorf("decode manifest: %w", err)
	}
	if dec.More() {
		return model.Manifest{}, fmt.Errorf("decode manifest: unexpected trailing content")
	}
	return m, nil
}

// ValidateSchema enforces every structural rule required before a manifest may
// be installed or trusted.
func ValidateSchema(m model.Manifest) error {
	if strings.TrimSpace(m.Scenario) == "" {
		return fmt.Errorf("manifest scenario must not be empty")
	}
	if m.Generation < 1 {
		return fmt.Errorf("manifest generation must be >= 1")
	}
	if len(m.Helpers) == 0 {
		return fmt.Errorf("manifest must declare at least one helper")
	}

	seenPaths := map[string]string{}
	seenEffects := map[string]string{}

	for name, h := range m.Helpers {
		if strings.TrimSpace(name) == "" {
			return fmt.Errorf("helper name must not be empty")
		}
		if err := validateRelativePath(h.RelativePath); err != nil {
			return fmt.Errorf("helper %q: %w", name, err)
		}
		if !sha256Re.MatchString(h.SHA256) {
			return fmt.Errorf("helper %q: sha256 must be 64 lowercase hex chars", name)
		}
		if h.Interpreter != AllowedInterpreter {
			return fmt.Errorf("helper %q: interpreter must be %s", name, AllowedInterpreter)
		}
		if !KnownEffects[h.Effect] {
			return fmt.Errorf("helper %q: unknown effect %q", name, h.Effect)
		}
		// Reject duplicate semantics: two helpers may not share a relative path
		// or an effect.
		if prev, ok := seenPaths[h.RelativePath]; ok {
			return fmt.Errorf("helpers %q and %q share relative_path %q", prev, name, h.RelativePath)
		}
		seenPaths[h.RelativePath] = name
		if prev, ok := seenEffects[h.Effect]; ok {
			return fmt.Errorf("helpers %q and %q share effect %q", prev, name, h.Effect)
		}
		seenEffects[h.Effect] = name
	}

	// Every policy action must map to a declared helper so authorization can
	// never point at a missing artifact.
	for principal, actions := range m.Policy {
		if strings.TrimSpace(principal) == "" {
			return fmt.Errorf("policy principal must not be empty")
		}
		for _, action := range actions {
			helperName := model.ActionToHelper(action)
			if _, ok := m.Helpers[helperName]; !ok {
				return fmt.Errorf("policy action %q references unknown helper %q", action, helperName)
			}
		}
	}
	return nil
}

func validateRelativePath(rel string) error {
	if rel == "" {
		return fmt.Errorf("relative_path must not be empty")
	}
	if rel == "." || rel == ".." {
		return fmt.Errorf("relative_path %q is not a filename", rel)
	}
	if strings.ContainsAny(rel, "/\\") {
		return fmt.Errorf("relative_path %q must be a single filename with no separators", rel)
	}
	if strings.Contains(rel, "\x00") {
		return fmt.Errorf("relative_path must not contain NUL")
	}
	return nil
}
