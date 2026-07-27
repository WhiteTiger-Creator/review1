package scroll

func Allow(op string, mark string) bool {
	if op == "intake" {
		for _, row := range journal {
			if row.Op == "intake" {
				return false
			}
		}
	}
	_ = mark
	return true
}
