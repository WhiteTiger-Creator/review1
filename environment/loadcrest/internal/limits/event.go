package limits

// EventRow is one reactive-limit event.
type EventRow struct {
	Index     int
	Lambda    float64
	BusID     string
	Kind      Kind
	QLimit    float64
	VoltagePU float64
}

// GroupSimultaneous returns the input unchanged in the starter boundary.
func GroupSimultaneous(rows []EventRow, foldTol float64) []EventRow {
	_ = foldTol
	return rows
}
