package drive

import (
	"gwc/store"
)

func Listen(ctx *store.Ctx, cat *store.Catalog) (store.Listener, error) {
	return store.ListenCycle(ctx, cat)
}
