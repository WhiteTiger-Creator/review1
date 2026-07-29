package gate

import "blkmir/store"

func applyChunk(out *store.StagePipe, span int) {
	out.Staged = span
}

func applyRoll(out *store.StagePipe, span int) {
	out.HolesCleared = true
	out.HoleSpan = span
}

func applyLatch(out *store.StagePipe) {
	out.ContentCaught = true
}

func wave_m(pipe *store.StagePipe, evt store.StageEvt, phase string) *store.StagePipe {
	out := *pipe
	switch phase {
	case "chunk":
		if evt.PresentMark {
			applyChunk(&out, evt.ByteSpan)
		}
	case "roll":
		if evt.HoleClearMark {
			applyRoll(&out, evt.ByteSpan)
		}
	case "latch":
		if evt.ContentMark {
			applyLatch(&out)
		}
	}
	return &out
}

func WaveStep(pipe *store.StagePipe, evt store.StageEvt, phase string) (*store.StagePipe, error) {
	return wave_m(pipe, evt, phase), nil
}
