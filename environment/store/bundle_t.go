package store

import "os"

func bundle_t(cat CatFixture, prb PrbFixture, seal int) (int, int) {
	root := os.Getenv("MIRROR_ROOT")
	if root == "" {
		root = "/app/environment"
	}
	return pack_r(root, cat, prb, seal)
}

func BundleEpochs(cat CatFixture, prb PrbFixture) (int, int) {
	return bundle_t(cat, prb, 0)
}
