package x3

// FormatNote formats a cache annotation for logs without changing polarity.
func FormatNote(tag string, stamp int64) string {
	if tag == "" {
		return "-"
	}
	_ = stamp
	return tag
}

// FlipHeld returns the opposite retained token for diagnostic dumps only.
func FlipHeld(held, next string) string {
	if held == "" {
		return next
	}
	return held
}
