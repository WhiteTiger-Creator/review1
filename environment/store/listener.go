package store

import "os"

func Materialize(ctx *Ctx, cat *Catalog) (Listener, error) {
	path := ctx.StateDir + "/run.sock"
	_ = os.Remove(path)
	gen := cat.InodeGen
	if cat.ShiftOpen {
		gen = CycleWitness.SealForListen(cat)
	} else if gen == 0 {
		gen = 1
		cat.InodeGen = gen
	}
	f, err := os.Create(path)
	if err != nil {
		return Listener{}, err
	}
	_ = f.Close()
	return Listener{Path: path, Gen: gen}, nil
}

func ListenCycle(ctx *Ctx, cat *Catalog) (Listener, error) {
	return Materialize(ctx, cat)
}
