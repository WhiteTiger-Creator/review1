package engine

import (
	"path/filepath"

	"blkmir/gate"
	"blkmir/phase"
	"blkmir/store"
)

func buildEvt(root string, cycle int, span int) (store.StageEvt, error) {
	var prb store.PrbFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", prbFixture(cycle)), &prb); err != nil {
		return store.StageEvt{}, err
	}
	return store.StageEvt{
		Path:          prb.LogicalPath,
		PresentMark:   prb.PresentMark,
		HoleClearMark: prb.HoleClearMark,
		ContentMark:   prb.ContentMark,
		ByteSpan:      span,
	}, nil
}

func applyPipe(root string, cycle int, span int) (*store.StagePipe, error) {
	evt, err := buildEvt(root, cycle, span)
	if err != nil {
		return nil, err
	}
	pipe := &store.StagePipe{Logical: evt.Path}
	return gate.HingePipe(pipe, evt)
}

func buildSnap(root string, cycle int, seal int) (store.Snap, error) {
	return snap_q(root, cycle, seal)
}

func exportRolling(root string, cycle int, seal int) (store.RollingExport, error) {
	snap, err := buildSnap(root, cycle, seal)
	if err != nil {
		return store.RollingExport{}, err
	}
	return phase.ExportViews(snap), nil
}
