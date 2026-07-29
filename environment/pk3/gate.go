package pk3

import "qdenv/internal"

func windowHasSeq(buf internal.FrameBuf, w internal.Window, seq int) bool {
	if w.Size <= 0 {
		return false
	}
	start := len(buf.Frames) - w.Size
	if start < 0 {
		start = 0
	}
	for i := start; i < len(buf.Frames); i++ {
		if buf.Frames[i].Seq == seq {
			return true
		}
	}
	return false
}

// FilterG filters re-sent frames against recent sequence window.
func FilterG(a internal.FrameBuf, b internal.Window, c internal.Seq) (internal.FrameBuf, error) {
	if len(a.Frames) == 0 {
		return a, nil
	}
	last := a.Frames[len(a.Frames)-1]
	if windowHasSeq(a, b, last.Seq) && last.Seq <= c.Last {
		a.Frames = a.Frames[:len(a.Frames)-1]
	}
	return a, nil
}
