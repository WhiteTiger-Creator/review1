package knot

func knot_p(book *Book, sid, iid string, mut bool) (float64, int, error) {
	if book == nil {
		return 0, 0, errNilBook
	}
	k := Key(sid, iid)
	w := book.W[k]
	band := BandOf(w, book.Cuts)
	if !mut {
		return w, band, nil
	}
	s := book.Sig[k]
	next := (1.0-book.Alpha)*w + book.Alpha*s
	if book.Frozen {
		book.Shadow[k] = next
		return w, band, nil
	}
	book.W[k] = next
	return w, band, nil
}

func ApplyKnot(book *Book, sid, iid string, mut bool) (float64, int, error) {
	return knot_p(book, sid, iid, mut)
}

func MarkFrozen(book *Book, on bool) {
	if book == nil {
		return
	}
	book.Frozen = on
}
