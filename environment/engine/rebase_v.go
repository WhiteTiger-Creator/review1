package engine

import "blkmir/store"

func rebase_v(outDir string, cycle int, cat store.CatFixture, prb store.PrbFixture) (int, int) {
	_, _, _ = outDir, cycle, prb
	return cat.Epoch - 1, cat.Epoch - 1
}

func RebaseFloors(outDir string, cycle int, cat store.CatFixture, prb store.PrbFixture) (int, int) {
	return rebase_v(outDir, cycle, cat, prb)
}
