#!/usr/bin/env bash
# Oracle solution: replaces broken files in /app with RFC 6962 compliant implementations.

set -euo pipefail

TARGET_DIR="/app"
if [ ! -d "$TARGET_DIR" ]; then
    TARGET_DIR="."
fi

cat << 'EOF' > "$TARGET_DIR/merkle.go"
package main

import (
	"crypto/sha256"
	"errors"
)

// HashLeaf computes the RFC 6962 Merkle tree leaf hash: SHA-256(0x00 || data).
func HashLeaf(data []byte) [32]byte {
	h := sha256.New()
	h.Write([]byte{0x00})
	h.Write(data)
	var result [32]byte
	copy(result[:], h.Sum(nil))
	return result
}

// HashNode computes the RFC 6962 Merkle tree internal node hash:
// SHA-256(0x01 || left || right).
func HashNode(left, right [32]byte) [32]byte {
	h := sha256.New()
	h.Write([]byte{0x01})
	h.Write(left[:])
	h.Write(right[:])
	var result [32]byte
	copy(result[:], h.Sum(nil))
	return result
}

// largestPowerOf2LessThan returns the largest power of 2 strictly less than n (for n > 1).
func largestPowerOf2LessThan(n uint64) uint64 {
	if n <= 1 {
		return 0
	}
	k := uint64(1)
	for k<<1 < n {
		k <<= 1
	}
	return k
}

// VerifyInclusion verifies an RFC 6962 §2.1.1 Merkle inclusion proof for arbitrary tree sizes.
// leafIndex is 0-based; proof is the sibling hashes from leaf level up to root.
func VerifyInclusion(leafData []byte, leafIndex, treeSize uint64, proof [][32]byte, expectedRoot [32]byte) error {
	if leafIndex >= treeSize {
		return errors.New("leaf index out of range")
	}
	current := HashLeaf(leafData)
	res, rem, err := evalInclusion(current, leafIndex, treeSize, proof)
	if err != nil {
		return err
	}
	if len(rem) != 0 {
		return errors.New("inclusion proof contains trailing unused hashes")
	}
	if res != expectedRoot {
		return errors.New("inclusion proof failed: root hash mismatch")
	}
	return nil
}

func evalInclusion(leafHash [32]byte, leafIndex, treeSize uint64, proof [][32]byte) ([32]byte, [][32]byte, error) {
	if treeSize == 1 {
		if leafIndex != 0 {
			return [32]byte{}, nil, errors.New("invalid leaf index")
		}
		return leafHash, proof, nil
	}
	k := largestPowerOf2LessThan(treeSize)
	if leafIndex < k {
		if len(proof) == 0 {
			return [32]byte{}, nil, errors.New("proof too short")
		}
		rSibling := proof[len(proof)-1]
		subProof := proof[:len(proof)-1]
		left, rem, err := evalInclusion(leafHash, leafIndex, k, subProof)
		if err != nil {
			return [32]byte{}, nil, err
		}
		return HashNode(left, rSibling), rem, nil
	} else {
		if len(proof) == 0 {
			return [32]byte{}, nil, errors.New("proof too short")
		}
		lSibling := proof[len(proof)-1]
		subProof := proof[:len(proof)-1]
		right, rem, err := evalInclusion(leafHash, leafIndex-k, treeSize-k, subProof)
		if err != nil {
			return [32]byte{}, nil, err
		}
		return HashNode(lSibling, right), rem, nil
	}
}

// VerifyConsistency verifies an RFC 6962 §2.1.2 Merkle consistency proof between
// a tree of snapshot1 leaves (root hash root1) and snapshot2 leaves (root hash root2).
func VerifyConsistency(snapshot1, snapshot2 uint64, root1, root2 [32]byte, proof [][32]byte) error {
	if snapshot1 > snapshot2 {
		return errors.New("first snapshot must not exceed second snapshot")
	}

	if snapshot1 == snapshot2 {
		if len(proof) != 0 {
			return errors.New("proof must be empty for equal-size trees")
		}
		if root1 != root2 {
			return errors.New("consistency check failed: roots differ for same tree size")
		}
		return nil
	}

	if snapshot1 == 0 {
		return nil
	}

	if len(proof) == 0 {
		return errors.New("consistency proof cannot be empty for different-sized trees")
	}

	fn := snapshot1 - 1
	sn := snapshot2 - 1

	for fn%2 == 1 {
		fn >>= 1
		sn >>= 1
	}

	fr := proof[0]
	sr := proof[0]

	for _, c := range proof[1:] {
		if sn == 0 {
			return errors.New("consistency proof is too long")
		}
		if fn%2 == 1 || fn == sn {
			fr = HashNode(c, fr)
			sr = HashNode(c, sr)
			for fn%2 == 0 && fn != 0 {
				fn >>= 1
				sn >>= 1
			}
		} else {
			sr = HashNode(sr, c)
		}
		fn >>= 1
		sn >>= 1
	}

	if fr != root1 {
		return errors.New("consistency proof failed: first root hash mismatch")
	}
	if sr != root2 {
		return errors.New("consistency proof failed: second root hash mismatch")
	}
	return nil
}
EOF

cat << 'EOF' > "$TARGET_DIR/sct.go"
package main

import (
	"bytes"
	"crypto"
	"crypto/ecdsa"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"time"
)

const maxClockSkewSecs = 300 // 5 minutes

// buildSCTSigningInput serializes the signed data for an SCT per RFC 6962 §3.2.
func buildSCTSigningInput(sct *SignedCertificateTimestamp, entry *LogEntry) []byte {
	var buf bytes.Buffer

	// Version (1 byte)
	buf.WriteByte(sct.SCTVersion)
	// SignatureType (1 byte = 0x00 = certificate_timestamp)
	buf.WriteByte(SigTypeCertificateTimestamp)

	// Timestamp (8 bytes, big-endian)
	binary.Write(&buf, binary.BigEndian, sct.Timestamp) //nolint:errcheck

	// LogEntryType (2 bytes)
	binary.Write(&buf, binary.BigEndian, entry.EntryType) //nolint:errcheck

	if entry.EntryType == EntryTypePreCert {
		buf.Write(entry.IssuerKeyHash[:])
	}

	// Certificate length (3 bytes, big-endian) + cert bytes
	cl := len(entry.CertData)
	buf.WriteByte(byte(cl >> 16))
	buf.WriteByte(byte(cl >> 8))
	buf.WriteByte(byte(cl))
	buf.Write(entry.CertData)

	// Extensions length (2 bytes) + extension bytes
	binary.Write(&buf, binary.BigEndian, uint16(len(sct.Extensions))) //nolint:errcheck
	buf.Write(sct.Extensions)

	return buf.Bytes()
}

// ValidateSCT verifies the signature on an SCT against the given log public key (ECDSA or RSA).
func ValidateSCT(sct *SignedCertificateTimestamp, entry *LogEntry, logKey crypto.PublicKey) error {
	if sct.Signature.HashAlg != 0 && sct.Signature.HashAlg != HashAlgSHA256 {
		return errors.New("unsupported hash algorithm for SCT signature")
	}

	skew := time.Duration(maxClockSkewSecs) * time.Second

	latestAcceptable := time.Now().Add(skew)
	if sct.Timestamp > uint64(latestAcceptable.UnixMilli()) {
		return errors.New("SCT timestamp rejected: too far in the future")
	}

	input := buildSCTSigningInput(sct, entry)
	digest := sha256.Sum256(input)

	switch key := logKey.(type) {
	case *ecdsa.PublicKey:
		if sct.Signature.SigAlg != 0 && sct.Signature.SigAlg != SigAlgECDSA {
			return errors.New("signature algorithm mismatch for ECDSA public key")
		}
		r, s, err := ParseECDSASignature(sct.Signature.Signature)
		if err != nil {
			return errors.New("failed to decode ECDSA signature: " + err.Error())
		}
		if !ecdsa.Verify(key, digest[:], r, s) {
			return errors.New("SCT ECDSA signature verification failed")
		}
	case *rsa.PublicKey:
		if sct.Signature.SigAlg != 0 && sct.Signature.SigAlg != SigAlgRSA {
			return errors.New("signature algorithm mismatch for RSA public key")
		}
		if err := rsa.VerifyPKCS1v15(key, crypto.SHA256, digest[:], sct.Signature.Signature); err != nil {
			return errors.New("SCT RSA signature verification failed: " + err.Error())
		}
	default:
		return errors.New("unsupported public key algorithm")
	}

	return nil
}
EOF

cat << 'EOF' > "$TARGET_DIR/ct.go"
package main

import (
	"crypto"
	"crypto/ecdsa"
	"crypto/rsa"
	"crypto/x509"
	"encoding/asn1"
	"encoding/binary"
	"errors"
	"math/big"
)

// RFC 6962 constants.
const (
	SCTVersion1                 = 0
	SigTypeCertificateTimestamp = 0
	SigTypeTreeHead             = 1
	EntryTypeX509               = 0
	EntryTypePreCert            = 1
	HashAlgSHA256               = 4
	SigAlgRSA                   = 1
	SigAlgECDSA                 = 3
)

// LogID is the 32-byte SHA-256 hash of the log's DER-encoded public key.
type LogID [32]byte

// DigitallySigned represents a TLS digitally-signed struct (RFC 5246 §4.7).
type DigitallySigned struct {
	HashAlg   uint8
	SigAlg    uint8
	Signature []byte
}

// SignedCertificateTimestamp represents a CT SCT (RFC 6962 §3.2).
type SignedCertificateTimestamp struct {
	SCTVersion uint8
	LogID      LogID
	Timestamp  uint64 // milliseconds since Unix epoch
	Extensions []byte
	Signature  DigitallySigned
}

// SignedTreeHead represents a CT Signed Tree Head (RFC 6962 §3.5).
type SignedTreeHead struct {
	Version        uint8
	TreeSize       uint64
	Timestamp      uint64
	SHA256RootHash [32]byte
	Signature      DigitallySigned
}

// LogEntry represents a parsed CT log entry (RFC 6962 §3.1).
type LogEntry struct {
	EntryType     uint16
	IssuerKeyHash [32]byte // 32-byte SHA-256 hash of issuer key (only for EntryTypePreCert)
	CertData      []byte   // CertData for EntryTypeX509, or TBSCertificate for EntryTypePreCert
	Extensions    []byte
}

// ParseSCT parses a TLS-serialized SignedCertificateTimestamp.
func ParseSCT(data []byte) (*SignedCertificateTimestamp, error) {
	if len(data) < 43 {
		return nil, errors.New("SCT data too short")
	}
	sct := &SignedCertificateTimestamp{}
	off := 0

	sct.SCTVersion = data[off]
	off++

	copy(sct.LogID[:], data[off:off+32])
	off += 32

	sct.Timestamp = binary.BigEndian.Uint64(data[off:])
	off += 8

	if off+2 > len(data) {
		return nil, errors.New("truncated extensions length")
	}
	extLen := int(binary.BigEndian.Uint16(data[off:]))
	off += 2
	if off+extLen > len(data) {
		return nil, errors.New("truncated extensions")
	}
	sct.Extensions = make([]byte, extLen)
	copy(sct.Extensions, data[off:off+extLen])
	off += extLen

	if off+4 > len(data) {
		return nil, errors.New("truncated signature header")
	}
	sct.Signature.HashAlg = data[off]
	off++
	sct.Signature.SigAlg = data[off]
	off++
	sigLen := int(binary.BigEndian.Uint16(data[off:]))
	off += 2
	if off+sigLen > len(data) {
		return nil, errors.New("truncated signature bytes")
	}
	sct.Signature.Signature = make([]byte, sigLen)
	copy(sct.Signature.Signature, data[off:off+sigLen])

	return sct, nil
}

// ParseLogEntry parses a CT log entry from its binary wire encoding.
func ParseLogEntry(data []byte) (*LogEntry, error) {
	if len(data) < 5 {
		return nil, errors.New("log entry too short")
	}
	entry := &LogEntry{}
	off := 0

	entry.EntryType = binary.BigEndian.Uint16(data[off:])
	off += 2

	if entry.EntryType == EntryTypePreCert {
		if off+32 > len(data) {
			return nil, errors.New("truncated issuer key hash")
		}
		copy(entry.IssuerKeyHash[:], data[off:off+32])
		off += 32
	}

	if off+3 > len(data) {
		return nil, errors.New("truncated certificate length")
	}
	certLen := int(data[off])<<16 | int(data[off+1])<<8 | int(data[off+2])
	off += 3
	if off+certLen > len(data) {
		return nil, errors.New("truncated certificate data")
	}
	entry.CertData = make([]byte, certLen)
	copy(entry.CertData, data[off:off+certLen])
	off += certLen

	if off+2 > len(data) {
		return nil, errors.New("missing extension length field")
	}
	extLen := int(data[off])<<8 | int(data[off+1])
	off += 2
	if off+extLen > len(data) {
		return nil, errors.New("truncated extensions data: declared length exceeds buffer")
	}
	entry.Extensions = make([]byte, extLen)
	copy(entry.Extensions, data[off:off+extLen])

	return entry, nil
}

// ParsePublicKey parses a DER-encoded public key (PKIX format).
func ParsePublicKey(der []byte) (crypto.PublicKey, error) {
	pub, err := x509.ParsePKIXPublicKey(der)
	if err != nil {
		return nil, err
	}
	switch pub.(type) {
	case *ecdsa.PublicKey, *rsa.PublicKey:
		return pub, nil
	default:
		return nil, errors.New("unsupported public key type")
	}
}

// ParseECDSASignature decodes a DER-encoded ECDSA signature into r and s.
func ParseECDSASignature(der []byte) (r, s *big.Int, err error) {
	var sig struct{ R, S *big.Int }
	if _, err = asn1.Unmarshal(der, &sig); err != nil {
		return nil, nil, err
	}
	return sig.R, sig.S, nil
}
EOF

cat << 'EOF' > "$TARGET_DIR/verifier.go"
package main

import (
	"context"
	"crypto"
	"errors"
	"sync"
)

// BatchVerifier verifies a collection of SCTs concurrently against a CT log's public key (ECDSA or RSA).
type BatchVerifier struct {
	logKey crypto.PublicKey
}

// NewBatchVerifier creates a BatchVerifier for the given CT log public key.
func NewBatchVerifier(logKey crypto.PublicKey) *BatchVerifier {
	return &BatchVerifier{
		logKey: logKey,
	}
}

// VerifyBatch concurrently verifies len(scts) SCTs against their corresponding log entries.
func (bv *BatchVerifier) VerifyBatch(scts []*SignedCertificateTimestamp, entries []*LogEntry) []error {
	return bv.VerifyBatchContext(context.Background(), scts, entries)
}

// VerifyBatchContext verifies SCTs concurrently using a worker pool while respecting context cancellation.
func (bv *BatchVerifier) VerifyBatchContext(ctx context.Context, scts []*SignedCertificateTimestamp, entries []*LogEntry) []error {
	if len(scts) != len(entries) {
		return []error{errors.New("scts and entries slice lengths do not match")}
	}

	errs := make([]error, len(scts))
	var wg sync.WaitGroup

	for i := range scts {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()

			select {
			case <-ctx.Done():
				errs[idx] = ctx.Err()
				return
			default:
			}

			errs[idx] = ValidateSCT(scts[idx], entries[idx], bv.logKey)
		}(i)
	}

	wg.Wait()
	return errs
}
EOF

echo "All RFC 6962 CT log auditor solution files written successfully."
