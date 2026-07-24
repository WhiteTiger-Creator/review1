package main

import (
	"encoding/hex"
	"encoding/pem"
	"flag"
	"fmt"
	"os"
)

func main() {
	logKeyPath := flag.String("log-key", "", "Path to PEM-encoded CT log ECDSA public key")
	sctPath := flag.String("sct", "", "Path to binary-encoded SCT file")
	entryPath := flag.String("entry", "", "Path to binary-encoded log entry file")
	flag.Parse()

	if *logKeyPath == "" || *sctPath == "" || *entryPath == "" {
		fmt.Fprintln(os.Stderr, "Usage: ctverify -log-key <pem> -sct <bin> -entry <bin>")
		os.Exit(1)
	}

	// Load log public key
	keyPEM, err := os.ReadFile(*logKeyPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading log key: %v\n", err)
		os.Exit(1)
	}
	block, _ := pem.Decode(keyPEM)
	if block == nil {
		fmt.Fprintln(os.Stderr, "Error: failed to decode PEM block from log key file")
		os.Exit(1)
	}
	logKey, err := ParsePublicKey(block.Bytes)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing log public key: %v\n", err)
		os.Exit(1)
	}

	// Load and parse SCT
	sctBytes, err := os.ReadFile(*sctPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading SCT file: %v\n", err)
		os.Exit(1)
	}
	sct, err := ParseSCT(sctBytes)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing SCT: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("SCT Log ID:   %s\n", hex.EncodeToString(sct.LogID[:]))
	fmt.Printf("SCT Timestamp: %d ms\n", sct.Timestamp)
	fmt.Printf("SCT Version:   %d\n", sct.SCTVersion)

	// Load and parse log entry
	entryBytes, err := os.ReadFile(*entryPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading entry file: %v\n", err)
		os.Exit(1)
	}
	entry, err := ParseLogEntry(entryBytes)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing log entry: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Entry type:   %d\n", entry.EntryType)
	fmt.Printf("Cert length:  %d bytes\n", len(entry.CertData))

	// Verify SCT
	if err := ValidateSCT(sct, entry, logKey); err != nil {
		fmt.Fprintf(os.Stderr, "SCT verification FAILED: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("SCT verification: OK")
}
