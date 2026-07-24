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
// For EntryTypePreCert (1), the entry payload contains IssuerKeyHash (32 bytes)
// followed by 24-bit TBSCertificate length prefix and data.
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
		// BROKEN: skipped copying IssuerKeyHash
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
	// BROKEN: missing bounds check on extLen
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
