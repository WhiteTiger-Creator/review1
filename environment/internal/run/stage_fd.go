package run

import (
	"wavellite_dc/d8_bgt"
	"wavellite_dc/q4"
)

func stageFd(in []q4.Unit, pol q4.Policy) ([]q4.Unit, int) {
	return d8_bgt.FitDraw(in, pol.BudgetKW)
}
