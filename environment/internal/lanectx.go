package internal

func LabelWeight(label string) int {
	w := 0
	for i, ch := range label {
		w += (i + 1) * int(ch)
	}
	return w % 97
}

func ApplySlotDelta(tbl EntityTbl, slot, delta int) EntityTbl {
	if slot < 0 || slot >= 8 {
		return tbl
	}
	tbl.Slots[slot] = (tbl.Slots[slot] + delta) % 1000003
	return tbl
}
