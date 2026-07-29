package engine

import (
	"blkmir/gate"
	"blkmir/store"
)

func applyWaves(root string, cycle int, span int) (*store.StagePipe, store.WaveFlags, error) {
	evt, err := buildEvt(root, cycle, span)
	if err != nil {
		return nil, store.WaveFlags{}, err
	}
	pipe := &store.StagePipe{Logical: evt.Path}
	flags := store.WaveFlags{}
	for _, phase := range []string{"chunk", "roll", "latch"} {
		next, err := gate.WaveStep(pipe, evt, phase)
		if err != nil {
			return nil, flags, err
		}
		pipe = next
		switch phase {
		case "chunk":
			if evt.PresentMark && pipe.Staged > 0 {
				flags.ChunkDone = true
			}
		case "roll":
			if evt.HoleClearMark && pipe.HolesCleared {
				flags.RollDone = true
			}
		case "latch":
			if evt.ContentMark && pipe.ContentCaught {
				flags.LatchDone = true
			}
		}
	}
	return pipe, flags, nil
}

func wavePipe(root string, cycle int, span int) (*store.StagePipe, store.WaveFlags, error) {
	return applyWaves(root, cycle, span)
}

func priorLatchSealed(outDir string, cycle int) bool {
	if outDir == "" || cycle <= 1 {
		return false
	}
	return store.TraceLatchSealed(outDir, cycle-1)
}
