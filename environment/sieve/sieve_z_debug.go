package sieve

// DebugFmt returns a short operator label without changing rows.
func DebugFmt(r Row) string {
	return r.Role + ":" + r.ItemID
}
