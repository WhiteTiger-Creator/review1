package n2

import (
	"encoding/json"
	"hxenv/lib/core"
	"os"
	"path/filepath"
)

func Replay(v string) (core.Snapshot, bool, error) {
	rows, e := Read(v)
	if e != nil {
		return core.Snapshot{}, false, e
	}
	var last core.Snapshot
	parent := ""
	for _, j := range rows {
		if j.Soft {
			continue
		}
		if j.ParentSeal != parent || j.PlanDigest != core.DigestPlan(j.Plan) {
			break
		}
		seal := core.RecordSeal(j)
		last = core.Snapshot{Journal: j, Seal: seal}
		parent = seal
	}
	return last, last.Seal != "", nil
}

func Save(v string, s core.Snapshot) error {
	if e := os.MkdirAll(v, 0755); e != nil {
		return e
	}
	b, e := json.Marshal(s)
	if e != nil {
		return e
	}
	return os.WriteFile(filepath.Join(v, "snapshot.json"), append(b, '\n'), 0644)
}

func LoadSnap(v string) (core.Snapshot, bool, error) {
	b, e := os.ReadFile(filepath.Join(v, "snapshot.json"))
	if os.IsNotExist(e) {
		return core.Snapshot{}, false, nil
	}
	if e != nil {
		return core.Snapshot{}, false, e
	}
	var s core.Snapshot
	if e = json.Unmarshal(b, &s); e != nil {
		return core.Snapshot{}, false, nil
	}
	return s, true, nil
}
