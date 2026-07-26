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
	j := core.Journal{
		Finger:     f,
		Plan:       p,
		Soft:       soft,
		PlanDigest: core.DigestPlan(p),
	}
	if soft {
		j.Kind = "soft"
		if ok {
			j.Seq = last.Journal.Seq + 1
			j.Epoch = last.Journal.Epoch
			j.ParentSeal = last.Seal
		} else {
			j.Seq = 1
			j.Epoch = 0
		}
	} else {
		j.Kind = "commit"
		if ok {
			j.Seq = last.Journal.Seq + 1
			j.Epoch = last.Journal.Epoch + 1
			j.ParentSeal = last.Seal
		} else {
			j.Seq = 1
			j.Epoch = 1
		}
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
	if soft {
		e = n2.WriteShade(v, n2.Shade{Finger: f, Plan: p, PlanDigest: j.PlanDigest})
		return s, e
	}
	if e = n2.Save(v, s); e != nil {
		return core.Snapshot{}, e
	}
	_ = n2.ClearShade(v)
	return s, nil
}
