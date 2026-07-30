package run

import (
	"wavellite_dc/q4"
	"wavellite_dc/y5_qrm"
)

func stageDr(in []q4.Unit, ledger []q4.Approval, pol q4.Policy) ([]q4.Unit, int) {
	return y5_qrm.DistinctRoles(in, ledger, q4.SignReq{
		Epoch:    pol.EvalEpoch,
		MinRoles: pol.MinRoles,
		Roles:    pol.RequiredRoles,
	})
}
