package engine

import (
	"path/filepath"

	"blkmir/store"
)

func snap_q(root string, cycle int, seal int) (store.Snap, error) {
	var cat store.CatFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", catFixture(cycle)), &cat); err != nil {
		return store.Snap{}, err
	}
	var prb store.PrbFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", prbFixture(cycle)), &prb); err != nil {
		return store.Snap{}, err
	}
	_ = seal
	return store.FuseViews(cat, prb, 0), nil
}
