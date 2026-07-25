package gate

import "blkmir/store"

func legacy_hinge(pipe *store.StagePipe, evt store.StageEvt) (*store.StagePipe, error) {
	out := *pipe
	if evt.HoleClearMark {
		out.Closed = true
		out.HoleSpan = evt.ByteSpan
	}
	return &out, nil
}

func LegacyHinge(pipe *store.StagePipe, evt store.StageEvt) (*store.StagePipe, error) {
	return legacy_hinge(pipe, evt)
}
