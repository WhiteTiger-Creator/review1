package gw

import (
	"qdenv/internal"
	"qdenv/pk3"
)

func applyGate(buf internal.FrameBuf, st internal.Frame) internal.FrameBuf {
	buf.Frames = append(buf.Frames, st)
	buf, _ = pk3.FilterG(buf, internal.Window{Size: 3}, internal.Seq{Last: st.Seq})
	return buf
}
