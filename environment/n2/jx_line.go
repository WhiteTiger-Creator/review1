package n2

import (
	"bufio"
	"encoding/json"
	"hxenv/lib/core"
	"os"
	"path/filepath"
)

func Path(v string) string { return filepath.Join(v, "ledger.jsonl") }

func Read(v string) ([]core.Journal, error) {
	f, e := os.Open(Path(v))
	if os.IsNotExist(e) {
		return nil, nil
	}
	if e != nil {
		return nil, e
	}
	defer f.Close()
	out := []core.Journal{}
	s := bufio.NewScanner(f)
	for s.Scan() {
		line := s.Bytes()
		if len(line) == 0 {
			continue
		}
		var j core.Journal
		if e = json.Unmarshal(line, &j); e != nil {
			continue
		}
		out = append(out, j)
	}
	return out, s.Err()
}

func Append(v string, j core.Journal) error {
	if e := os.MkdirAll(v, 0755); e != nil {
		return e
	}
	f, e := os.OpenFile(Path(v), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if e != nil {
		return e
	}
	defer f.Close()
	b, _ := json.Marshal(j)
	_, e = f.Write(append(b, '\n'))
	return e
}

func RewriteValid(v string) error {
	rows, e := Read(v)
	if e != nil {
		return e
	}
	f, e := os.Create(Path(v))
	if e != nil {
		return e
	}
	defer f.Close()
	for _, j := range rows {
		b, _ := json.Marshal(j)
		if _, e = f.Write(append(b, '\n')); e != nil {
			return e
		}
	}
	return nil
}

func Squash(v string) error {
	rows, e := Read(v)
	if e != nil {
		return e
	}
	if len(rows) == 0 {
		return nil
	}
	tip := rows[len(rows)-1]
	tip.ParentSeal = ""
	tip.Epoch = 1
	f, e := os.Create(Path(v))
	if e != nil {
		return e
	}
	defer f.Close()
	b, _ := json.Marshal(tip)
	_, e = f.Write(append(b, '\n'))
	if e != nil {
		return e
	}
	return Save(v, core.Snapshot{Journal: tip, Seal: core.RecordSeal(tip)})
}

func StripSoft(v string) error { return nil }
