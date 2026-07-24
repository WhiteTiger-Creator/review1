package grid

import (
	"math"
	"math/cmplx"

	"loadcrest/internal/deck"
)

// Branch holds topology and pi-model primitives.
type Branch struct {
	ID       string
	From     string
	To       string
	Status   deck.BranchStatus
	R        float64
	X        float64
	BTotal   float64
	Tap      float64
	ShiftDeg float64
	Yff      complex128
	Yft      complex128
	Ytf      complex128
	Ytt      complex128
}

// BranchesFromDeck builds branch models and computes in-service primitives.
func BranchesFromDeck(n *deck.Network) []Branch {
	out := make([]Branch, len(n.Branches))
	for i, br := range n.Branches {
		b := Branch{
			ID: br.ID, From: br.From, To: br.To, Status: br.Status,
			R: br.R, X: br.X, BTotal: br.BTotal, Tap: br.Tap, ShiftDeg: br.ShiftDeg,
		}
		if br.Status == deck.BranchIN {
			y := 1 / complex(br.R, br.X)
			shift := br.ShiftDeg * deg2rad
			a := cmplx.Rect(br.Tap, shift)
			ysh := complex(0, br.BTotal/2)
			abs2 := real(a)*real(a) + imag(a)*imag(a)
			b.Yff = (y + ysh) / complex(abs2, 0)
			b.Yft = -y / cmplx.Conj(a)
			b.Ytf = -y / a
			b.Ytt = y + ysh
		}
		out[i] = b
	}
	return out
}

// PrimitiveRow is the sorted admittance companion branch row.
type PrimitiveRow struct {
	ID                         string
	From, To                   string
	Status                     string
	Gff, Bff, Gft, Bft         float64
	Gtf, Btf, Gtt, Btt         float64
}

// PrimitiveRows returns sorted nonzero-capable primitive inventory for all branches.
func PrimitiveRows(brs []Branch) []PrimitiveRow {
	rows := make([]PrimitiveRow, len(brs))
	for i, b := range brs {
		rows[i] = PrimitiveRow{
			ID: b.ID, From: b.From, To: b.To, Status: string(b.Status),
			Gff: real(b.Yff), Bff: imag(b.Yff),
			Gft: real(b.Yft), Bft: imag(b.Yft),
			Gtf: real(b.Ytf), Btf: imag(b.Ytf),
			Gtt: real(b.Ytt), Btt: imag(b.Ytt),
		}
		_ = math.Abs
	}
	return rows
}
