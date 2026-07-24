package main

import (
	"crypto/sha256"
	"errors"
)

// HashLeaf computes the RFC 6962 Merkle tree leaf hash: SHA-256(0x00 || data).
func HashLeaf(data []byte) [32]byte {
	h := sha256.New()
	// BROKEN: missing 0x00 domain separator byte
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

	// BROKEN: Uses simple index%2 bit-shifting which fails on non-power-of-two trees and inverts order
	index := leafIndex
	for _, sibling := range proof {
		if index%2 == 0 {
			current = HashNode(sibling, current)
		} else {
			current = HashNode(current, sibling)
		}
		index >>= 1
	}

	if current != expectedRoot {
		return errors.New("inclusion proof failed: root hash mismatch")
	}
	return nil
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
		// BROKEN: returns nil without comparing root1 != root2
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
