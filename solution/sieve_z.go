package sieve

import (
	"sort"
	"strconv"

	"cqrun/internal/util"
	"cqrun/knot"
)

func sieve_z(items []ItemRef, forbidden map[string]bool, trainN int) (train []ItemRef, eval []ItemRef, err error) {
	if items == nil {
		return nil, nil, errNilPlan
	}
	n := len(items)
	if trainN < 0 || trainN > n {
		trainN = n / 2
	}
	evalN := n - trainN
	candidates := make([]ItemRef, 0, n)
	for _, it := range items {
		if forbidden != nil && forbidden[knot.Key(it.SID, it.IID)] {
			continue
		}
		candidates = append(candidates, it)
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].W == candidates[j].W {
			return candidates[i].IID < candidates[j].IID
		}
		return candidates[i].W < candidates[j].W
	})
	if len(candidates) < evalN {
		return nil, nil, errNilPlan
	}
	eval = append([]ItemRef(nil), candidates[:evalN]...)
	evalSet := map[string]bool{}
	for _, e := range eval {
		evalSet[knot.Key(e.SID, e.IID)] = true
	}
	remain := make([]ItemRef, 0, n)
	for _, it := range items {
		if evalSet[knot.Key(it.SID, it.IID)] {
			continue
		}
		remain = append(remain, it)
	}
	sort.SliceStable(remain, func(i, j int) bool {
		if remain[i].W == remain[j].W {
			return remain[i].IID < remain[j].IID
		}
		return remain[i].W > remain[j].W
	})
	if len(remain) < trainN {
		return nil, nil, errNilPlan
	}
	train = append([]ItemRef(nil), remain[:trainN]...)
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
