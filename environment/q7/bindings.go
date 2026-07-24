package q7

// RowInput is one load row for scaling helpers.
type RowInput struct {
	ID   string  `json:"id"`
	Force float64 `json:"force"`
	AuxA  float64 `json:"aux_a"`
	AuxB  float64 `json:"aux_b"`
}

// ScratchArena holds ephemeral per-run buffers.
type ScratchArena struct {
	Path string
	Buf  map[string]float64
}
