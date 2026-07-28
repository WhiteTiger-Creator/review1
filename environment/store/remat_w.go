package store

// RematWitness tracks inode generation across shift open, listener seal, and
// cycle release. Cookie minting and listener materialization must agree on the
// sealed generation for each rematerialization.
type RematWitness struct {
	pending  uint64
	sealed   uint64
	armEpoch uint64
}

var CycleWitness RematWitness

func (w *RematWitness) ArmBeforeShift(cat *Catalog) uint64 {
	w.pending = cat.InodeGen
	cat.InodeGen++
	return cat.InodeGen
}

func (w *RematWitness) SealForListen(cat *Catalog) uint64 {
	gen := w.pending
	if gen == 0 {
		gen = 1
	}
	w.sealed = gen
	cat.InodeGen = gen
	return gen
}

func (w *RematWitness) ReleaseShift(cat *Catalog) {
	cat.ShiftOpen = false
	if w.sealed > 0 {
		w.pending = w.sealed - 1
	}
}

func (w *RematWitness) MintGen(gen uint64) uint64 {
	if w.sealed > 0 {
		return w.sealed
	}
	return gen
}

func (w *RematWitness) ObservedGen(cat *Catalog) uint64 {
	if w.sealed > 0 {
		return w.sealed
	}
	return cat.InodeGen
}

func (w *RematWitness) Sealed() uint64 {
	return w.sealed
}

func (w *RematWitness) ArmEpoch() uint64 {
	return w.armEpoch
}

func OpenShiftWitness(cat *Catalog) {
	CycleWitness.ArmBeforeShift(cat)
}

func CloseShiftWitness(cat *Catalog) {
	CycleWitness.ReleaseShift(cat)
}
