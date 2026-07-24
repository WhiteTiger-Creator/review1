package main

import (
	"context"
	"crypto"
	"crypto/sha256"
	"errors"
	"hash"
	"sync"
)

// BatchVerifier verifies a collection of SCTs concurrently against a CT log's public key (ECDSA or RSA).
type BatchVerifier struct {
	logKey crypto.PublicKey
	hasher hash.Hash
}

// NewBatchVerifier creates a BatchVerifier for the given CT log public key.
func NewBatchVerifier(logKey crypto.PublicKey) *BatchVerifier {
	return &BatchVerifier{
		logKey: logKey,
		hasher: sha256.New(),
	}
}

// VerifyBatch concurrently verifies len(scts) SCTs against their corresponding log entries.
// Returns a slice of errors; nil at index i means scts[i] is valid.
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

			// BROKEN 1: shared bv.hasher across goroutines causes data race
			// BROKEN 2: ignores ctx.Err() or cancellation
			input := buildSCTSigningInput(scts[idx], entries[idx])

			bv.hasher.Reset()
			bv.hasher.Write(input)
			digest := bv.hasher.Sum(nil)

			errs[idx] = ValidateSCT(scts[idx], entries[idx], bv.logKey)
			_ = digest
		}(i)
	}

	wg.Wait()
	return errs
}
