package captureload

import "cdnqual/framestream"

// LoadCapture is the capture load stage entry (loads frames for stitch).
func LoadCapture(path string) ([]framestream.Packet, error) {
	return framestream.LoadPCAP(path)
}
