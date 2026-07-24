package loader

type Record struct {
	Feed         string
	TripID       string
	RouteID      string
	StartDate    string
	ReceivedTS   string
	IngestTS     string
	Schedule     string
	StopsRaw     string
	BadSequence  bool
	BadTimestamp bool
	Quarantine   bool
	HasSkipped   bool
}

func LoadAll(_ string) ([]Record, error) {
	return []Record{}, nil
}
