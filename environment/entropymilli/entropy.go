package entropymilli

// Of returns Shannon entropy of payload in milli-bits (floored).
// Baseline returns 0.
func Of(payload []byte) int {
	_ = payload
	return 0
}
