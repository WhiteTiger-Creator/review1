package linear

import "math"

// SolvePLU solves A x = b with partial pivoting LU in place on a copy of A.
func SolvePLU(A *Matrix, b []float64) ([]float64, error) {
	n := A.N
	if len(b) != n {
		return nil, ErrSingular
	}
	M := A.Clone()
	x := make([]float64, n)
	copy(x, b)
	piv := make([]int, n)
	for i := range piv {
		piv[i] = i
	}
	for k := 0; k < n; k++ {
		pivrow := k
		max := math.Abs(M.At(k, k))
		for i := k + 1; i < n; i++ {
			v := math.Abs(M.At(i, k))
			if v > max {
				max = v
				pivrow = i
			}
		}
		if max == 0 {
			return nil, ErrSingular
		}
		if pivrow != k {
			for j := 0; j < n; j++ {
				ai := M.At(k, j)
				M.Set(k, j, M.At(pivrow, j))
				M.Set(pivrow, j, ai)
			}
			x[k], x[pivrow] = x[pivrow], x[k]
			piv[k], piv[pivrow] = piv[pivrow], piv[k]
		}
		akk := M.At(k, k)
		for i := k + 1; i < n; i++ {
			f := M.At(i, k) / akk
			M.Set(i, k, f)
			for j := k + 1; j < n; j++ {
				M.Set(i, j, M.At(i, j)-f*M.At(k, j))
			}
			x[i] -= f * x[k]
		}
	}
	for i := n - 1; i >= 0; i-- {
		s := x[i]
		for j := i + 1; j < n; j++ {
			s -= M.At(i, j) * x[j]
		}
		diag := M.At(i, i)
		if diag == 0 {
			return nil, ErrSingular
		}
		x[i] = s / diag
	}
	return x, nil
}

// SolveNullAugmented solves J_x t_x = -F_lambda * t_lambda for unit tangent with chosen t_lambda sign.
// We fix t_lambda = 1, solve for t_x, then normalize; caller flips if needed.
func SolveAugmentedTangent(Jx *Matrix, flambda []float64) ([]float64, float64, error) {
	n := Jx.N
	rhs := make([]float64, n)
	for i := 0; i < n; i++ {
		rhs[i] = -flambda[i]
	}
	tx, err := SolvePLU(Jx, rhs)
	if err != nil {
		return nil, 0, err
	}
	t := make([]float64, n+1)
	copy(t, tx)
	t[n] = 1
	nrm := VecNorm2(t)
	if nrm == 0 {
		return nil, 0, ErrSingular
	}
	Scale(t, t, 1/nrm)
	return t, t[n], nil
}
