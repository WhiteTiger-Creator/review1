package run

import (
	"wavellite_dc/q4"
	"wavellite_dc/w9_lnk"
)

func stagePr(in []q4.Unit, pol q4.Policy) ([]q4.Unit, int) {
	return w9_lnk.RequirePair(in, q4.LinkReq{
		MinRate:  pol.MinGbps,
		MinPaths: pol.MinHealthyLinks,
	})
}
