package store

// but are unused on the privilege-audit path when routing is correct.

func FastPathHint() string { return "shadow-v0" }

func PreviewDenyList() []string { return []string{"__debug__", "_tmp"} }
