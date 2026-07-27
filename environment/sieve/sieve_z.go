package sieve

import (
	"sort"
	"strconv"

	"cqrun/internal/util"
	"cqrun/knot"
)

func sieve_z(items []ItemRef, forbidden map[string]bool, trainN int) (train []ItemRef, eval []ItemRef, err error) {
	_ = forbidden
	if items == nil {
		return nil, nil, errNilPlan
	}
	n := len(items)
	if trainN < 0 || trainN > n {
		trainN = n / 2
	}
	evalN := n - trainN
	cp := append([]ItemRef(nil), items...)
	sort.SliceStable(cp, func(i, j int) bool {
		if cp[i].W == cp[j].W {
			return cp[i].IID < cp[j].IID
		}
		return cp[i].W < cp[j].W
	})
	eval = append([]ItemRef(nil), cp[:evalN]...)
	rest := append([]ItemRef(nil), cp[evalN:]...)
	sort.SliceStable(rest, func(i, j int) bool {
		if rest[i].W == rest[j].W {
			return rest[i].IID < rest[j].IID
		}
		return rest[i].W > rest[j].W
	})
	train = rest
	if len(train) > trainN {
		train = train[:trainN]
	}
	return train, eval, nil
}

func ApplySieve(items []ItemRef, forbidden map[string]bool, trainN int) (train []ItemRef, eval []ItemRef, err error) {
	return sieve_z(items, forbidden, trainN)
}

func StampRow(sid, iid string, epoch int, role string, band int, w float64, forbidden map[string]bool, decimals int) Row {
	bit := 0
	if role == "eval" {
		if forbidden[knot.Key(sid, iid)] {
			bit = 1
		}
	}
	ah := AdmitHex(sid, iid, epoch, role, band)
	return Row{
		ScenarioID: sid,
		Epoch:      epoch,
		ItemID:     iid,
		Band:       band,
		Role:       role,
		AdmitHex:   ah,
		FenceHex:   FenceHex(ah, bit),
		Weight:     roundW(w, decimals),
	}
}

func roundW(w float64, decimals int) float64 {
	s := util.FmtWeight(w, decimals)
	out, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return w
	}
	return out
}
