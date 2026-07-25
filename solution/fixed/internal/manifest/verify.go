package manifest

import (
	"crypto/ed25519"
	"encoding/hex"
	"fmt"
	"strings"
)

// DecodePublicKey accepts either a raw 32-byte ed25519 public key or its hex
// encoding.
func DecodePublicKey(raw []byte) (ed25519.PublicKey, error) {
	if len(raw) == ed25519.PublicKeySize {
		return ed25519.PublicKey(append([]byte{}, raw...)), nil
	}
	decoded, err := hex.DecodeString(strings.TrimSpace(string(raw)))
	if err != nil {
		return nil, fmt.Errorf("public key is neither raw %d bytes nor hex: %w", ed25519.PublicKeySize, err)
	}
	if len(decoded) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("public key must be %d bytes, got %d", ed25519.PublicKeySize, len(decoded))
	}
	return ed25519.PublicKey(decoded), nil
}

// DecodeSignature accepts either a raw 64-byte signature or its hex encoding.
func DecodeSignature(raw []byte) ([]byte, error) {
	if len(raw) == ed25519.SignatureSize {
		return append([]byte{}, raw...), nil
	}
	decoded, err := hex.DecodeString(strings.TrimSpace(string(raw)))
	if err != nil {
		return nil, fmt.Errorf("signature is neither raw %d bytes nor hex: %w", ed25519.SignatureSize, err)
	}
	if len(decoded) != ed25519.SignatureSize {
		return nil, fmt.Errorf("signature must be %d bytes, got %d", ed25519.SignatureSize, len(decoded))
	}
	return decoded, nil
}

// VerifySignature verifies an ed25519 signature over the exact manifest bytes.
func VerifySignature(manifestBytes, sigRaw, pubRaw []byte) error {
	pub, err := DecodePublicKey(pubRaw)
	if err != nil {
		return err
	}
	sig, err := DecodeSignature(sigRaw)
	if err != nil {
		return err
	}
	if !ed25519.Verify(pub, manifestBytes, sig) {
		return fmt.Errorf("manifest signature verification failed")
	}
	return nil
}
