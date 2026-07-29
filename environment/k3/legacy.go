package k3

// DenseSum returns the total of all live page counts in st.
func DenseSum(st *Buf) int {
	if st == nil || st.Live == nil {
		return 0
	}
	n := 0
	for _, p := range st.Live {
		n += p
	}
	return n
}
