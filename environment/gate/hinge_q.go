package gate

import "blkmir/store"

func hinge_q(pipe *store.StagePipe, evt store.StageEvt) (*store.StagePipe, error) {
	mid := shift_s(pipe, evt)
	out := finalize_pipe(mid)
	return out, nil
}

func HingePipe(pipe *store.StagePipe, evt store.StageEvt) (*store.StagePipe, error) {
	return hinge_q(pipe, evt)
}
