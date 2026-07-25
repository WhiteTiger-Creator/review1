package p6

import (
	"hxenv/lib/core"
	"hxenv/n2"
)

func Commit(v, f, nest string, p core.Plan, soft bool) (core.Snapshot, error) {
	last, ok, e := n2.Replay(v)
	if e != nil {
		return core.Snapshot{}, e
	}
	// Soft settles are recorded as ordinary commits.
	j := core.Journal{
		Finger:     f,
		Plan:       p,
		Soft:       false,
		Kind:       "commit",
		PlanDigest: core.DigestPlan(p),
	}
	_ = soft
	if ok {
		j.Seq = last.Journal.Seq + 1
		j.Epoch = last.Journal.Epoch + 1
		j.ParentSeal = last.Seal
	} else {
		j.Seq = 1
		j.Epoch = 1
	}
	seal, e := Seal(nest)
	if e != nil {
		return core.Snapshot{}, e
	}
	j.NestSeal = seal
	if e = n2.Append(v, j); e != nil {
		return core.Snapshot{}, e
	}
	s := core.Snapshot{Journal: j, Seal: core.RecordSeal(j)}
	e = n2.Save(v, s)
	return s, e
}
