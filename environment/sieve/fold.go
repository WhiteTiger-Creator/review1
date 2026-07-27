package sieve

import (
	"sort"

	"cqrun/internal/util"
	"cqrun/knot"
)

func AdmitHex(sid, iid string, epoch int, role string, band int) string {
	return util.Sha16(sid + "|" + iid + "|" + itoa(epoch) + "|" + role + "|" + itoa(band))
}

func FenceHex(admit string, bit int) string {
	return util.Sha16(admit + "|" + itoa(bit))
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	sign := ""
	if n < 0 {
		sign = "-"
		n = -n
	}
	var d []byte
	for n > 0 {
		d = append([]byte{byte('0' + n%10)}, d...)
		n /= 10
	}
	return sign + string(d)
}

func FoldRows(rows []Row, epochs, walDepth, decimals int, book *knot.Book) Summary {
	hexes := make([]string, 0, len(rows))
	status := "sealed"
	for _, r := range rows {
		hexes = append(hexes, r.AdmitHex)
		if r.Role == "eval" {
			zero := FenceHex(r.AdmitHex, 0)
			if r.FenceHex != zero {
				status = "leaky"
			}
		}
	}
	sort.Strings(hexes)
	cohort := util.Sha16(util.HexJoin(hexes, ","))

	keys := make([]string, 0, len(book.W))
	for k := range book.W {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, k := range keys {
		parts = append(parts, k+":"+util.FmtWeight(book.W[k], decimals))
	}
	resume := util.Sha16(util.HexJoin(parts, ","))
	return Summary{
		Epochs:       epochs,
		RowsTotal:    len(rows),
		CohortDigest: cohort,
		ResumeDigest: resume,
		FenceStatus:  status,
		WalDepth:     walDepth,
	}
}
