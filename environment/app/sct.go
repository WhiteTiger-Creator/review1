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
// For EntryTypeX509 (0):
//   Version (1) | SigType(1=0) | Timestamp(8) | EntryType(2=0) | len(cert)(3) | cert | len(ext)(2) | ext
// For EntryTypePreCert (1):
//   Version (1) | SigType(1=0) | Timestamp(8) | EntryType(2=1) | IssuerKeyHash(32) | len(tbs)(3) | tbs | len(ext)(2) | ext
func buildSCTSigningInput(sct *SignedCertificateTimestamp, entry *LogEntry) []byte {
	var buf bytes.Buffer

	// Version (1 byte)
	buf.WriteByte(sct.SCTVersion)
	// BROKEN: missing SignatureType byte (0x00 = certificate_timestamp)

	// Timestamp (8 bytes, big-endian)
	binary.Write(&buf, binary.BigEndian, sct.Timestamp) //nolint:errcheck

	// LogEntryType (2 bytes)
	binary.Write(&buf, binary.BigEndian, entry.EntryType) //nolint:errcheck

	if entry.EntryType == EntryTypePreCert {
		// BROKEN: missing IssuerKeyHash (32 bytes) for PreCert entries
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

	// BROKEN: rejects past timestamps instead of future ones
	oldestAcceptable := time.Now().Add(-skew)
	if sct.Timestamp < uint64(oldestAcceptable.UnixMilli()) {
		return errors.New("SCT timestamp rejected: timestamp is too old")
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
		// BROKEN: returns error for RSA keys
		return errors.New("RSA log public key verification not implemented")
	default:
		return errors.New("unsupported public key algorithm")
	}

	return nil
}
