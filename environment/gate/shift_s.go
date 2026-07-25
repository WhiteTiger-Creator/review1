package gate

import "blkmir/store"

func applyPresent(out *store.StagePipe, span int) {
	out.Staged = span
	out.Closed = true
}

func applyHoleClear(out *store.StagePipe, span int) {
	out.HolesCleared = true
	out.HoleSpan = span
}

func applyContent(out *store.StagePipe) {
	out.ContentCaught = true
}

func shift_s(pipe *store.StagePipe, evt store.StageEvt) *store.StagePipe {
	out := *pipe
	if evt.PresentMark {
		applyPresent(&out, evt.ByteSpan)
	}
	if evt.HoleClearMark {
		applyHoleClear(&out, evt.ByteSpan)
	}
	if evt.ContentMark {
		applyContent(&out)
	}
	return &out
}

func finalize_pipe(pipe *store.StagePipe) *store.StagePipe {
	out := *pipe
	if out.HolesCleared && out.ContentCaught {
		out.Closed = true
	}
	return &out
}
