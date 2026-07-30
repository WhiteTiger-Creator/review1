package run

import (
	"wavellite_dc/g6_hst"
	"wavellite_dc/q4"
)

func stageBa(in []q4.Unit, pol q4.Policy) ([]q4.Unit, int) {
	return g6_hst.MatchFloors(in, q4.HostReq{
		MinNodes: pol.MinNodes,
		Firmware: pol.AllowedFirmware,
	})
}
