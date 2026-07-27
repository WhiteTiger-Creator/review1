package knot

// ShadowDiag reports shadow-copy drift for operator dashboards.
func ShadowDiag(book *Book) int {
	if book == nil {
		return 0
	}
	n := 0
	for k, w := range book.W {
		if book.Shadow[k] != w {
			n++
		}
	}
	return n
}
