package q7

// MapU applies a multiplicative transform across all rows.
func MapU(rows []RowInput, factor float64) []RowInput {
	out := make([]RowInput, len(rows))
	copy(out, rows)
	for i := range out {
		out[i].Force = out[i].Force * factor
		if i > 0 {
			out[i].AuxA = out[i].AuxA * factor
		}
	}
	return out
}
