package vault

import "errors"

var errNilLedger = errors.New("nil ledger")

type Entry struct {
	Epoch int     `json:"epoch"`
	SID   string  `json:"sid"`
	IID   string  `json:"iid"`
	Role  string  `json:"role"`
	Band  int     `json:"band"`
	WPre  float64 `json:"w_pre"`
}

type Ledger struct {
	Path     string
	Entries  []Entry
	Barrier  int
	SnapW    map[string]float64
	TrustSnap bool
}

func Key(sid, iid string) string {
	return sid + "/" + iid
}
