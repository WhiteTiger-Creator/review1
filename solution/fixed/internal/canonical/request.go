// Package canonical parses caller requests and derives their stable identity.
package canonical

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"

	"privhelper/internal/model"
)

// requestDigestPrefix is a version tag that binds a digest to this request
// schema. Changing the schema must change this prefix.
const requestDigestPrefix = "privhelper-request-v1"

// ParseRequest decodes a single request object, rejecting unknown fields and
// validating that every field is present and free of NUL bytes.
func ParseRequest(data []byte) (model.Request, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()

	var req model.Request
	if err := dec.Decode(&req); err != nil {
		return model.Request{}, fmt.Errorf("decode request: %w", err)
	}
	// Reject trailing content after the first JSON value.
	if dec.More() {
		return model.Request{}, fmt.Errorf("decode request: unexpected trailing content")
	}
	if err := ValidateRequest(req); err != nil {
		return model.Request{}, err
	}
	return req, nil
}

// ValidateRequest enforces the request field invariants.
func ValidateRequest(req model.Request) error {
	fields := map[string]string{
		"request_id": req.RequestID,
		"principal":  req.Principal,
		"action":     req.Action,
		"unit":       req.Unit,
	}
	for name, value := range fields {
		if value == "" {
			return fmt.Errorf("request field %q must not be empty", name)
		}
		if strings.ContainsRune(value, '\x00') {
			return fmt.Errorf("request field %q must not contain NUL", name)
		}
	}
	return nil
}

// Digest computes the SHA-256 hex digest that uniquely identifies the request
// body. The pre-image is a NUL-delimited, versioned concatenation of the
// request fields, which prevents field-boundary ambiguity.
func Digest(req model.Request) string {
	var b bytes.Buffer
	b.WriteString(requestDigestPrefix)
	b.WriteByte(0)
	b.WriteString(req.RequestID)
	b.WriteByte(0)
	b.WriteString(req.Principal)
	b.WriteByte(0)
	b.WriteString(req.Action)
	b.WriteByte(0)
	b.WriteString(req.Unit)

	sum := sha256.Sum256(b.Bytes())
	return hex.EncodeToString(sum[:])
}
