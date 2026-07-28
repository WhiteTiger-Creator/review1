package walops

// FilterApplied skips duplicate op_id lines and returns first-seen ops with counters.
func FilterApplied(ops []Op) (toRun []Op, applied, skipped int64) {
	seen := map[string]bool{}
	for _, op := range ops {
		if seen[op.OpID] {
			skipped++
			continue
		}
		seen[op.OpID] = true
		toRun = append(toRun, op)
		applied++
	}
	return toRun, applied, skipped
}
