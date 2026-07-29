package m7

import "qdenv/internal"

func IsBoundary(t internal.Tag) bool {
	return t.Boundary
}

func TagFromFrame(f internal.Frame) internal.Tag {
	return internal.Tag{Boundary: f.Boundary, Seq: f.Seq}
}
