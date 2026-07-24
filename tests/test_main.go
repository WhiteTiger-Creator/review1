package main

import (
	"context"
	"crypto"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/asn1"
	"encoding/binary"
	"fmt"
	"math/big"
	"os"
	"sync"
	"time"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: test_runner <test_name>")
		os.Exit(1)
	}
	switch os.Args[1] {
	case "leaf_hash":
		testLeafHash()
	case "inclusion_proof":
		testInclusionProof()
	case "sct_signing_format":
		testSCTSigningFormat()
	case "timestamp_validation":
		testTimestampValidation()
	case "consistency_equal_size":
		testConsistencyEqualSize()
	case "batch_race":
		testBatchRace()
	case "malformed_entry":
		testMalformedEntry()
	default:
		fmt.Fprintf(os.Stderr, "Unknown test: %s\n", os.Args[1])
		os.Exit(1)
	}
}

func mustSignECDSA(priv *ecdsa.PrivateKey, msg []byte) []byte {
	digest := sha256.Sum256(msg)
	r, s, err := ecdsa.Sign(rand.Reader, priv, digest[:])
	if err != nil {
		panic(err)
	}
	der, err := asn1.Marshal(struct{ R, S *big.Int }{r, s})
	if err != nil {
		panic(err)
	}
	return der
}

func mustSignRSA(priv *rsa.PrivateKey, msg []byte) []byte {
	digest := sha256.Sum256(msg)
	sig, err := rsa.SignPKCS1v15(rand.Reader, priv, crypto.SHA256, digest[:])
	if err != nil {
		panic(err)
	}
	return sig
}

func correctSigningInput(sct *SignedCertificateTimestamp, entry *LogEntry) []byte {
	buf := make([]byte, 0, 128)
	buf = append(buf, sct.SCTVersion)
	buf = append(buf, SigTypeCertificateTimestamp)
	ts := make([]byte, 8)
	binary.BigEndian.PutUint64(ts, sct.Timestamp)
	buf = append(buf, ts...)
	et := make([]byte, 2)
	binary.BigEndian.PutUint16(et, entry.EntryType)
	buf = append(buf, et...)
	if entry.EntryType == EntryTypePreCert {
		buf = append(buf, entry.IssuerKeyHash[:]...)
	}
	cl := len(entry.CertData)
	buf = append(buf, byte(cl>>16), byte(cl>>8), byte(cl))
	buf = append(buf, entry.CertData...)
	extLen := make([]byte, 2)
	binary.BigEndian.PutUint16(extLen, uint16(len(sct.Extensions)))
	buf = append(buf, extLen...)
	buf = append(buf, sct.Extensions...)
	return buf
}

// ── Test 1: Leaf Hash RFC 6962 domain separator ──────────────────────────────

func testLeafHash() {
	expected := sha256.Sum256([]byte{0x00})
	got := HashLeaf([]byte{})
	if got != expected {
		fmt.Printf("FAILED: HashLeaf([]) = %x\n  want %x\n", got, expected)
		os.Exit(1)
	}

	expected2 := sha256.Sum256(append([]byte{0x00}, []byte("hello")...))
	got2 := HashLeaf([]byte("hello"))
	if got2 != expected2 {
		fmt.Printf("FAILED: HashLeaf(\"hello\") = %x\n  want %x\n", got2, expected2)
		os.Exit(1)
	}

	fmt.Println("LEAF_HASH_OK")
}

// ── Test 2: Inclusion Proof (arbitrary non-power-of-two trees) ────────────────

func largestPowerOf2LessThanRef(n uint64) uint64 {
	if n <= 1 {
		return 0
	}
	k := uint64(1)
	for k<<1 < n {
		k <<= 1
	}
	return k
}

func buildRFCTree(leaves [][32]byte) [32]byte {
	n := uint64(len(leaves))
	if n == 0 {
		return sha256.Sum256(nil)
	}
	if n == 1 {
		return leaves[0]
	}
	k := largestPowerOf2LessThanRef(n)
	left := buildRFCTree(leaves[:k])
	right := buildRFCTree(leaves[k:])
	return HashNode(left, right)
}

func rfcInclusionProof(leafIdx uint64, leaves [][32]byte) [][32]byte {
	n := uint64(len(leaves))
	if n <= 1 {
		return nil
	}
	k := largestPowerOf2LessThanRef(n)
	if leafIdx < k {
		proof := rfcInclusionProof(leafIdx, leaves[:k])
		return append(proof, buildRFCTree(leaves[k:]))
	} else {
		proof := rfcInclusionProof(leafIdx-k, leaves[k:])
		return append(proof, buildRFCTree(leaves[:k]))
	}
}

func testInclusionProof() {
	// Test 1: 4-leaf tree
	rawLeaves4 := [][]byte{{0x01}, {0x02}, {0x03}, {0x04}}
	leafHashes4 := make([][32]byte, 4)
	for i, v := range rawLeaves4 {
		h := sha256.New()
		h.Write([]byte{0x00})
		h.Write(v)
		copy(leafHashes4[i][:], h.Sum(nil))
	}
	root4 := buildRFCTree(leafHashes4)

	proof4_0 := rfcInclusionProof(0, leafHashes4)
	if err := VerifyInclusion(rawLeaves4[0], 0, 4, proof4_0, root4); err != nil {
		fmt.Printf("FAILED: VerifyInclusion 4-leaf index 0: %v\n", err)
		os.Exit(1)
	}

	proof4_3 := rfcInclusionProof(3, leafHashes4)
	if err := VerifyInclusion(rawLeaves4[3], 3, 4, proof4_3, root4); err != nil {
		fmt.Printf("FAILED: VerifyInclusion 4-leaf index 3: %v\n", err)
		os.Exit(1)
	}

	// Test 2: Non-power-of-two 7-leaf tree (RFC 6962 §2.1.1 sub-tree math)
	rawLeaves7 := [][]byte{{0x10}, {0x20}, {0x30}, {0x40}, {0x50}, {0x60}, {0x70}}
	leafHashes7 := make([][32]byte, 7)
	for i, v := range rawLeaves7 {
		h := sha256.New()
		h.Write([]byte{0x00})
		h.Write(v)
		copy(leafHashes7[i][:], h.Sum(nil))
	}
	root7 := buildRFCTree(leafHashes7)

	for idx := uint64(0); idx < 7; idx++ {
		proof := rfcInclusionProof(idx, leafHashes7)
		if err := VerifyInclusion(rawLeaves7[idx], idx, 7, proof, root7); err != nil {
			fmt.Printf("FAILED: VerifyInclusion 7-leaf index %d: %v\n", idx, err)
			os.Exit(1)
		}
	}

	fmt.Println("INCLUSION_PROOF_OK")
}

// ── Test 3: SCT Signature Format (X509 & PreCert) ───────────────────────────

func computeLogID(pub crypto.PublicKey) LogID {
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		return sha256.Sum256([]byte("default-log-key"))
	}
	return sha256.Sum256(der)
}

func testSCTSigningFormat() {
	// 1. ECDSA X509 Entry
	privECDSA, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	logIDECDSA := computeLogID(&privECDSA.PublicKey)
	entryX509 := &LogEntry{
		EntryType: EntryTypeX509,
		CertData:  []byte("cert-bytes"),
	}
	sctX509 := &SignedCertificateTimestamp{
		SCTVersion: SCTVersion1,
		LogID:      logIDECDSA,
		Timestamp:  uint64(time.Now().UnixMilli()),
		Extensions: []byte{},
	}
	inputX509 := correctSigningInput(sctX509, entryX509)
	sctX509.Signature = DigitallySigned{
		HashAlg:   HashAlgSHA256,
		SigAlg:    SigAlgECDSA,
		Signature: mustSignECDSA(privECDSA, inputX509),
	}
	if err := ValidateSCT(sctX509, entryX509, &privECDSA.PublicKey); err != nil {
		fmt.Printf("FAILED: ValidateSCT rejected X509 ECDSA SCT: %v\n", err)
		os.Exit(1)
	}

	// 2. PreCert Entry with IssuerKeyHash
	var keyHash [32]byte
	kh := sha256.Sum256([]byte("issuer-pubkey"))
	copy(keyHash[:], kh[:])
	entryPreCert := &LogEntry{
		EntryType:     EntryTypePreCert,
		IssuerKeyHash: keyHash,
		CertData:      []byte("tbs-certificate-bytes"),
	}
	sctPreCert := &SignedCertificateTimestamp{
		SCTVersion: SCTVersion1,
		LogID:      logIDECDSA,
		Timestamp:  uint64(time.Now().UnixMilli()),
		Extensions: []byte{},
	}
	inputPreCert := correctSigningInput(sctPreCert, entryPreCert)
	sctPreCert.Signature = DigitallySigned{
		HashAlg:   HashAlgSHA256,
		SigAlg:    SigAlgECDSA,
		Signature: mustSignECDSA(privECDSA, inputPreCert),
	}
	if err := ValidateSCT(sctPreCert, entryPreCert, &privECDSA.PublicKey); err != nil {
		fmt.Printf("FAILED: ValidateSCT rejected PreCert SCT with IssuerKeyHash: %v\n", err)
		os.Exit(1)
	}

	// 3. RSA Signature Support
	privRSA, _ := rsa.GenerateKey(rand.Reader, 2048)
	logIDRSA := computeLogID(&privRSA.PublicKey)
	sctRSA := &SignedCertificateTimestamp{
		SCTVersion: SCTVersion1,
		LogID:      logIDRSA,
		Timestamp:  uint64(time.Now().UnixMilli()),
		Extensions: []byte{},
	}
	inputRSA := correctSigningInput(sctRSA, entryX509)
	sctRSA.Signature = DigitallySigned{
		HashAlg:   HashAlgSHA256,
		SigAlg:    SigAlgRSA,
		Signature: mustSignRSA(privRSA, inputRSA),
	}
	if err := ValidateSCT(sctRSA, entryX509, &privRSA.PublicKey); err != nil {
		fmt.Printf("FAILED: ValidateSCT rejected RSA signed SCT: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("SCT_SIGNING_FORMAT_OK")
}

// ── Test 4: SCT Timestamp Validation ─────────────────────────────────────────

func testTimestampValidation() {
	priv, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	logID := computeLogID(&priv.PublicKey)
	entry := &LogEntry{EntryType: EntryTypeX509, CertData: []byte("cert")}

	futureTS := uint64(time.Now().Add(365 * 24 * time.Hour).UnixMilli())
	futureSCT := &SignedCertificateTimestamp{
		SCTVersion: SCTVersion1,
		LogID:      logID,
		Timestamp:  futureTS,
		Extensions: []byte{},
	}
	futureInput := correctSigningInput(futureSCT, entry)
	futureSCT.Signature = DigitallySigned{
		HashAlg:   HashAlgSHA256,
		SigAlg:    SigAlgECDSA,
		Signature: mustSignECDSA(priv, futureInput),
	}
	if err := ValidateSCT(futureSCT, entry, &priv.PublicKey); err == nil {
		fmt.Println("FAILED: ValidateSCT accepted a future-dated SCT (1 year ahead)")
		os.Exit(1)
	}

	recentTS := uint64(time.Now().Add(-1 * time.Second).UnixMilli())
	recentSCT := &SignedCertificateTimestamp{
		SCTVersion: SCTVersion1,
		LogID:      logID,
		Timestamp:  recentTS,
		Extensions: []byte{},
	}
	recentInput := correctSigningInput(recentSCT, entry)
	recentSCT.Signature = DigitallySigned{
		HashAlg:   HashAlgSHA256,
		SigAlg:    SigAlgECDSA,
		Signature: mustSignECDSA(priv, recentInput),
	}
	if err := ValidateSCT(recentSCT, entry, &priv.PublicKey); err != nil {
		fmt.Printf("FAILED: ValidateSCT rejected a recent valid SCT: %v\n", err)
		os.Exit(1)
	}

	oldTS := uint64(time.Now().Add(-180 * 24 * time.Hour).UnixMilli())
	oldSCT := &SignedCertificateTimestamp{
		SCTVersion: SCTVersion1,
		LogID:      logID,
		Timestamp:  oldTS,
		Extensions: []byte{},
	}
	oldInput := correctSigningInput(oldSCT, entry)
	oldSCT.Signature = DigitallySigned{
		HashAlg:   HashAlgSHA256,
		SigAlg:    SigAlgECDSA,
		Signature: mustSignECDSA(priv, oldInput),
	}
	if err := ValidateSCT(oldSCT, entry, &priv.PublicKey); err != nil {
		fmt.Printf("FAILED: ValidateSCT rejected a 6-month-old SCT (valid): %v\n", err)
		os.Exit(1)
	}

	fmt.Println("TIMESTAMP_VALIDATION_OK")
}

// ── Test 5: Consistency Proof Equal-Size Root Check ───────────────────────────

func testConsistencyEqualSize() {
	var root1, root2 [32]byte
	copy(root1[:], "root-aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
	copy(root2[:], "root-bbbbbbbbbbbbbbbbbbbbbbbbbbbb")

	err := VerifyConsistency(4, 4, root1, root2, nil)
	if err == nil {
		fmt.Println("FAILED: VerifyConsistency accepted different roots for same tree size")
		os.Exit(1)
	}

	err = VerifyConsistency(4, 4, root1, root1, nil)
	if err != nil {
		fmt.Printf("FAILED: VerifyConsistency rejected matching roots for same tree size: %v\n", err)
		os.Exit(1)
	}

	proof := [][32]byte{root1}
	err = VerifyConsistency(4, 4, root1, root1, proof)
	if err == nil {
		fmt.Println("FAILED: VerifyConsistency accepted non-empty proof for equal-size trees")
		os.Exit(1)
	}

	err = VerifyConsistency(8, 4, root1, root2, nil)
	if err == nil {
		fmt.Println("FAILED: VerifyConsistency accepted snapshot1 > snapshot2")
		os.Exit(1)
	}

	fmt.Println("CONSISTENCY_EQUAL_SIZE_OK")
}

// ── Test 6: Concurrent BatchVerifier Context & Thread-Safety ─────────────────

func testBatchRace() {
	priv, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	logID := computeLogID(&priv.PublicKey)

	const N = 40
	scts := make([]*SignedCertificateTimestamp, N)
	entries := make([]*LogEntry, N)
	for i := 0; i < N; i++ {
		e := &LogEntry{
			EntryType: EntryTypeX509,
			CertData:  []byte(fmt.Sprintf("cert-%d", i)),
		}
		s := &SignedCertificateTimestamp{
			SCTVersion: SCTVersion1,
			LogID:      logID,
			Timestamp:  uint64(time.Now().UnixMilli()),
			Extensions: []byte{},
		}
		input := correctSigningInput(s, e)
		s.Signature = DigitallySigned{
			HashAlg:   HashAlgSHA256,
			SigAlg:    SigAlgECDSA,
			Signature: mustSignECDSA(priv, input),
		}
		scts[i] = s
		entries[i] = e
	}

	bv := NewBatchVerifier(&priv.PublicKey)

	var wg sync.WaitGroup
	results := make([][]error, 10)
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			results[idx] = bv.VerifyBatchContext(ctx, scts, entries)
		}(i)
	}

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(10 * time.Second):
		fmt.Println("FAILED: BatchVerify timed out")
		os.Exit(1)
	}

	for batch, errs := range results {
		for i, err := range errs {
			if err != nil {
				fmt.Printf("FAILED: batch %d, SCT %d: %v\n", batch, i, err)
				os.Exit(1)
			}
		}
	}

	fmt.Println("BATCH_RACE_OK")
}

// ── Test 7: Malformed Log Entry Parsing ──────────────────────────────────────

func testMalformedEntry() {
	// 1. Truncated PreCert IssuerKeyHash
	preCertTrunc := []byte{0x00, 0x01, 0xAA, 0xBB} // EntryTypePreCert, only 2 bytes of keyhash
	_, err := ParseLogEntry(preCertTrunc)
	if err == nil {
		fmt.Println("FAILED: ParseLogEntry accepted truncated PreCert IssuerKeyHash")
		os.Exit(1)
	}

	// 2. Oversized extLen panic test
	cert := []byte{0xAA}
	extLenClaimed := 9999
	buf := make([]byte, 0, 20)
	buf = append(buf, 0x00, 0x00)                 // EntryTypeX509
	buf = append(buf, 0x00, 0x00, 0x01)           // certLen = 1
	buf = append(buf, cert...)                    // cert data
	buf = append(buf, byte(extLenClaimed>>8), byte(extLenClaimed))
	buf = append(buf, 0x01, 0x02, 0x03, 0x04, 0x05)

	func() {
		defer func() {
			if r := recover(); r != nil {
				fmt.Printf("FAILED: ParseLogEntry panicked on malformed input: %v\n", r)
				os.Exit(1)
			}
		}()
		_, err := ParseLogEntry(buf)
		if err == nil {
			fmt.Printf("FAILED: ParseLogEntry accepted malformed input with extLen=%d\n", extLenClaimed)
			os.Exit(1)
		}
	}()

	// 3. Valid PreCert Entry Parsing
	var validKeyHash [32]byte
	copy(validKeyHash[:], []byte("01234567890123456789012345678901"))
	validPreCertBuf := make([]byte, 0, 50)
	validPreCertBuf = append(validPreCertBuf, 0x00, 0x01)           // EntryTypePreCert
	validPreCertBuf = append(validPreCertBuf, validKeyHash[:]...)    // IssuerKeyHash (32)
	validPreCertBuf = append(validPreCertBuf, 0x00, 0x00, 0x04)     // tbsLen = 4
	validPreCertBuf = append(validPreCertBuf, 0xDE, 0xAD, 0xBE, 0xEF)// tbs bytes
	validPreCertBuf = append(validPreCertBuf, 0x00, 0x01)           // extLen = 1
	validPreCertBuf = append(validPreCertBuf, 0xFF)                 // ext byte

	preEntry, err := ParseLogEntry(validPreCertBuf)
	if err != nil {
		fmt.Printf("FAILED: ParseLogEntry rejected valid PreCert entry: %v\n", err)
		os.Exit(1)
	}
	if preEntry.EntryType != EntryTypePreCert || preEntry.IssuerKeyHash != validKeyHash || len(preEntry.CertData) != 4 {
		fmt.Printf("FAILED: ParseLogEntry parsed wrong PreCert fields: %v\n", preEntry)
		os.Exit(1)
	}

	fmt.Println("MALFORMED_ENTRY_OK")
}
