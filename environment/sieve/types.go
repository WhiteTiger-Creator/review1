package sieve

import "errors"

var errNilPlan = errors.New("nil plan")

type Row struct {
	ScenarioID string  `json:"scenario_id"`
	Epoch      int     `json:"epoch"`
	ItemID     string  `json:"item_id"`
	Band       int     `json:"band"`
	Role       string  `json:"role"`
	AdmitHex   string  `json:"admit_hex"`
	FenceHex   string  `json:"fence_hex"`
	Weight     float64 `json:"weight"`
}

type Summary struct {
	Epochs       int    `json:"epochs"`
	RowsTotal    int    `json:"rows_total"`
	CohortDigest string `json:"cohort_digest"`
	ResumeDigest string `json:"resume_digest"`
	FenceStatus  string `json:"fence_status"`
	WalDepth     int    `json:"wal_depth"`
}

type Trace struct {
	Rows    []Row   `json:"rows"`
	Summary Summary `json:"summary"`
}

type ItemRef struct {
	SID string
	IID string
	W   float64
}
