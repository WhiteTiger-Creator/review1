package linear

import (
	"fmt"
	"math"
)

// Matrix is a dense row-major matrix.
type Matrix struct {
	N    int
	Data []float64
}

// NewMatrix allocates an n×n matrix.
func NewMatrix(n int) *Matrix {
	return &Matrix{N: n, Data: make([]float64, n*n)}
}

// At returns element (i,j).
func (m *Matrix) At(i, j int) float64 { return m.Data[i*m.N+j] }

// Set sets element (i,j).
func (m *Matrix) Set(i, j int, v float64) { m.Data[i*m.N+j] = v }

// Add adds v into element (i,j).
func (m *Matrix) Add(i, j int, v float64) { m.Data[i*m.N+j] += v }

// Clone returns a deep copy.
func (m *Matrix) Clone() *Matrix {
	out := NewMatrix(m.N)
	copy(out.Data, m.Data)
	return out
}

// VecDot is the Euclidean inner product.
func VecDot(a, b []float64) float64 {
	s := 0.0
	for i := range a {
		s += a[i] * b[i]
	}
	return s
}

// VecNorm2 is the Euclidean norm.
func VecNorm2(a []float64) float64 {
	return math.Sqrt(VecDot(a, a))
}

// Scale copies s*a into out.
func Scale(out, a []float64, s float64) {
	for i := range a {
		out[i] = a[i] * s
	}
}

// Axpy does y = y + a*x
func Axpy(y, x []float64, a float64) {
	for i := range y {
		y[i] += a * x[i]
	}
}

// ErrSingular marks a singular pivot.
var ErrSingular = fmt.Errorf("singular matrix")
