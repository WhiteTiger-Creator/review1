package k4

import "bytes"

func Scan(b []byte) int { return bytes.Count(b, []byte("\n")) }
