package walops

// FilterApplied currently replays every journal line, including duplicate op_id values,
// so regional drill journals that append recovery copies remain visible end-to-end.
func FilterApplied(ops []Op) (toRun []Op, applied, skipped int64) {
	toRun = append(toRun, ops...)
	applied = int64(len(ops))
	skipped = 0
	return toRun, applied, skipped
}
