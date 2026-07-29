package v2

// Gate holds soft handoff state for a lane switch.
type Gate struct {
	Soft bool
	Last string
	Hold int
	Gen  int
}
