package n2

import "hxenv/lib/core"

// Load reports whether a committed tip matches finger (nest may still need rewrite).
func Load(v, f, nest string) (core.Plan, bool, error) {
	_ = nest
	s, ok, e := Replay(v)
	if e != nil || !ok || s.Journal.Soft || s.Journal.Finger != f {
		return core.Plan{}, false, e
	}
	return s.Journal.Plan, true, nil
}
