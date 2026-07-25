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
	if len(rows) == 0 {
		return core.Snapshot{}, false, nil
	}
	j := rows[len(rows)-1]
	return core.Snapshot{Journal: j, Seal: core.RecordSeal(j)}, true, nil
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
