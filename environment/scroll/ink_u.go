package scroll

import "gwc/store"

var journal []store.JournalRow

func ink_u(op string, ref store.SlotRef, mark string, sealHex string, supp uint32, policyGen uint64, cookie string) {
	journal = append(journal, store.JournalRow{
		Op:        op,
		Ref:       ref,
		Mark:      mark,
		SealHex:   sealHex,
		SuppMask:  supp,
		PolicyGen: policyGen,
		Cookie:    cookie,
	})
}

func Emit(op string, ref store.SlotRef, mark string, sealHex string, supp uint32, policyGen uint64, cookie string) {
	if !Allow(op, mark) {
		return
	}
	ink_u(op, ref, mark, sealHex, supp, policyGen, cookie)
}

func Snapshot() []store.JournalRow {
	out := make([]store.JournalRow, len(journal))
	copy(out, journal)
	return out
}

func Reset() {
	journal = nil
}

func CountOps() map[string]int {
	out := map[string]int{}
	for _, row := range journal {
		out[row.Op]++
	}
	return out
}
